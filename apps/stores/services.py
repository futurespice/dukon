"""
Business-logic services for the stores app.

FAT VIEW FIX: SetTariffPlanView and ActivatePromocodeView previously contained
business logic (price lookups, balance mutations, transaction creation) directly
in the view layer. This module extracts that logic into pure service functions
that are:
  - Independently testable
  - Reusable from management commands, Celery tasks, or admin actions
  - Free of HTTP concerns (no request/response objects)
"""
import logging
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from django.db import transaction
from django.utils import timezone

from apps.stores.models import Store, StoreBalanceTransaction, StoreTariffPlan, Promocode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tariff price matrix
# ---------------------------------------------------------------------------

# Moved from SetTariffPlanView class attributes into module-level constants so
# they can be referenced from tests, management commands, and the admin.
# Key: (tariff_code, duration_code) → price in KGS
TARIFF_PRICES: dict[tuple[str, str], int] = {
    # FREE — always 0
    ('0', '1'): 0, ('0', '2'): 0, ('0', '3'): 0, ('0', '4'): 0,
    # BASIC
    ('1', '1'): 990,  ('1', '2'): 2700,  ('1', '3'): 5400,  ('1', '4'): 9900,
    # STANDARD
    ('2', '1'): 1990, ('2', '2'): 5700,  ('2', '3'): 10800, ('2', '4'): 19900,
    # PREMIUM
    ('3', '1'): 4990, ('3', '2'): 14700, ('3', '3'): 27000, ('3', '4'): 49900,
}

# Duration code → number of calendar months
TARIFF_DURATION_MONTHS: dict[str, int] = {
    '1': 1,
    '2': 3,
    '3': 6,
    '4': 12,
}


class TariffError(Exception):
    """Raised when a tariff purchase cannot proceed."""


def get_tariff_price(tariff: str, duration_type: str) -> int:
    """
    Return the price in KGS for the given tariff + duration combination.
    Raises TariffError for unknown combinations.
    """
    key = (tariff, duration_type)
    if key not in TARIFF_PRICES:
        raise TariffError(
            f'Недопустимая комбинация тарифа ({tariff}) и длительности ({duration_type}).'
        )
    return TARIFF_PRICES[key]


@transaction.atomic
def purchase_tariff(store: Store, tariff: str, duration_type: str, idempotency_key: str = None) -> StoreTariffPlan:
    """
    Deduct the tariff cost from the store's balance, create a StoreTariffPlan
    record, and log a StoreBalanceTransaction — all in one atomic block.

    M-1 FIX: Re-fetch the Store row with select_for_update() inside this
    function so it is safe regardless of whether the caller already holds a
    lock.  Previously the function relied on the caller passing a pre-locked
    instance; any call from a management command, admin action, or Celery task
    that skipped the lock could race with a concurrent purchase and allow
    balance to go negative.

    Args:
        store:         Store instance — used only to obtain the PK.
                       The locked row is re-fetched inside this function.
        tariff:        Store.TariffPlan choice value (e.g. '1' for BASIC).
        duration_type: StoreTariffPlan.DurationType choice value (e.g. '2' for 3 months).

    Returns:
        The newly created StoreTariffPlan instance.

    Raises:
        TariffError: if the combination is invalid, the tariff is already active,
                     or the balance is insufficient.
    """
    # M-1 FIX: always acquire a row-level lock on the Store regardless of caller.
    store = Store.objects.select_for_update().get(pk=store.pk)

    amount = get_tariff_price(tariff, duration_type)
    months = TARIFF_DURATION_MONTHS.get(duration_type, 1)

    if store.tariff_plan == tariff:
        raise TariffError(
            f'Тарифный план «{Store.TariffPlan(tariff).label}» уже активен для этого магазина.'
        )

    if store.balance < amount:
        raise TariffError(
            f'Недостаточно средств. Нужно {amount}, доступно {store.balance}.'
        )

    balance_before = store.balance
    store.balance -= Decimal(amount)
    store.tariff_plan = tariff
    store.save(update_fields=['balance', 'tariff_plan'])

    start_date = timezone.now()
    end_date = start_date + relativedelta(months=months)

    tariff_plan = StoreTariffPlan.objects.create(
        store=store,
        tariff_plan=tariff,
        start_date=start_date,
        end_date=end_date,
        amount=amount,
        duration_type=duration_type,
    )

    StoreBalanceTransaction.objects.create(
        store=store,
        amount=amount,
        transaction_type=StoreBalanceTransaction.TransactionType.OUTCOME,
        description=f'Покупка тарифа {tariff} на {months} мес.',
        balance_before=balance_before,
        balance_after=store.balance,
        type=StoreBalanceTransaction.PaymentType.BUY_TARIF,
        status=StoreBalanceTransaction.Status.SUCCESS,
        idempotency_key=idempotency_key,
    )

    logger.info(
        'tariff_purchased store=%s tariff=%s duration=%s amount=%s balance_after=%s',
        store.uuid, tariff, duration_type, amount, store.balance,
    )
    return tariff_plan


# ---------------------------------------------------------------------------
# Promocode activation
# ---------------------------------------------------------------------------

class PromocodeError(Exception):
    """Raised when a promocode cannot be activated."""


@transaction.atomic
def activate_promocode(store: Store, code_value: str, idempotency_key: str = None) -> Decimal:
    """
    Validate the promocode, add its amount to the store's balance, and create
    a StoreBalanceTransaction — all in one atomic block.

    M-1/M-2 FIX: Re-fetch the Store row with select_for_update() inside this
    function so it is safe regardless of whether the caller already holds a
    lock.  Balance is incremented via a single atomic UPDATE with F() rather
    than a Python-level read-modify-write to guard against any future caller
    that omits the pre-lock.

    Args:
        store:      Store instance — used only to obtain the PK.
                    The locked row is re-fetched inside this function.
        code_value: The raw promocode string entered by the user.

    Returns:
        The credited amount (Decimal).

    Raises:
        PromocodeError: if the code is not found, already used, or doesn't belong
                        to this store.
    """
    from django.db.models import F as _F

    # M-1/M-2 FIX: always acquire a row-level lock on the Store regardless of caller.
    store = Store.objects.select_for_update().get(pk=store.pk)

    try:
        promo = (
            Promocode.objects
            .select_for_update()
            .get(code=code_value, store=store, is_used=False)
        )
    except Promocode.DoesNotExist:
        raise PromocodeError('Промокод не найден или уже использован.')

    # FIX (MEDIUM — non-positive promocode amount → IntegrityError → 500):
    # Promocode.amount has no MinValueValidator, so an admin or raw SQL could
    # create a promo with amount=0 or amount=-500. Applying such a promo:
    #   - amount=0:   no-op balance update but a misleading SUCCESS log.
    #   - amount<0:   balance DECREASES, violating store_balance_non_negative
    #                 CheckConstraint → IntegrityError → unhandled 500.
    #                 The view only catches PromocodeError, not IntegrityError.
    # Fix: validate before touching the balance.
    if promo.amount <= Decimal('0'):
        logger.error(
            'activate_promocode: promocode %s on store %s has non-positive amount=%s — '
            'rejecting to prevent balance corruption.',
            code_value, store.uuid, promo.amount,
        )
        raise PromocodeError(
            'Промокод имеет некорректную сумму. Обратитесь в службу поддержки.'
        )

    balance_before = store.balance

    # M-2 FIX: use a single atomic F()-based UPDATE instead of Python
    # read-modify-write.  refresh_from_db() fetches the committed value so
    # balance_after recorded in the transaction log is always accurate.
    Store.objects.filter(pk=store.pk).update(balance=_F('balance') + promo.amount)
    store.refresh_from_db(fields=['balance'])

    StoreBalanceTransaction.objects.create(
        store=store,
        amount=promo.amount,
        transaction_type=StoreBalanceTransaction.TransactionType.INCOME,
        description=f'Активация промокода {code_value}',
        balance_before=balance_before,
        balance_after=store.balance,
        type=StoreBalanceTransaction.PaymentType.OTHER,
        status=StoreBalanceTransaction.Status.SUCCESS,
        idempotency_key=idempotency_key,
    )

    promo.is_used = True
    promo.used_at = timezone.now()
    promo.save(update_fields=['is_used', 'used_at'])

    logger.info(
        'promocode_activated store=%s code=%s amount=%s',
        store.uuid, code_value, promo.amount,
    )
    return promo.amount


# ---------------------------------------------------------------------------
# Slide limit helper (extracted from perform_create fat logic)
# ---------------------------------------------------------------------------

_MAX_SLIDES_PER_STORE = 20


def check_slide_limit(store: Store) -> None:
    """
    Raises DRFValidationError if the store already has the maximum number of slides.

    WARNING: this function does NOT acquire a row-level lock and is therefore
    unsafe under concurrency — 100 parallel calls will all read the same count
    and all pass the check. Use create_slide_locked() for production code.
    This function is retained only for unit tests that run synchronously.
    """
    from rest_framework.exceptions import ValidationError as DRFValidationError
    count = store.slides.count()
    if count >= _MAX_SLIDES_PER_STORE:
        raise DRFValidationError(
            f'Максимум {_MAX_SLIDES_PER_STORE} слайдов на магазин.'
        )


@transaction.atomic
def create_slide_locked(store: Store, slide_fields: dict) -> 'Slide':
    """
    R-2 FIX (TOCTOU — Slide Limit Race Condition):
    The previous pattern called check_slide_limit() (unlocked count) then
    serializer.save() in two separate transactions. Under 100 parallel
    POST /slides/ requests all 100 read count=19, all pass the check, and
    all create a slide — resulting in 119 slides against a limit of 20.

    Fix: lock the Store row with select_for_update() FIRST, then count slides,
    then INSERT — all in one atomic block. PostgreSQL's FOR UPDATE prevents
    any other transaction from inserting a slide for the same store until
    this transaction commits. The slide count seen here is always authoritative.

    Args:
        store:        Store instance — used only to obtain the PK.
                      The locked row is re-fetched inside this function.
        slide_fields: dict of validated slide field values (title, image,
                      sort_order, etc.) — does NOT include 'store' (set here).

    Returns:
        The newly created Slide instance.

    Raises:
        DRFValidationError: if the store already has _MAX_SLIDES_PER_STORE slides.
    """
    from apps.stores.models import Slide
    from rest_framework.exceptions import ValidationError as DRFValidationError

    # Lock the Store row so no concurrent transaction can insert a slide
    # for this store until we commit. This serialises all parallel requests.
    locked_store = Store.objects.select_for_update().get(pk=store.pk)

    # Count is now authoritative: we hold the lock, so no other transaction
    # can change the slide count for this store while we're checking.
    current_count = locked_store.slides.count()
    if current_count >= _MAX_SLIDES_PER_STORE:
        raise DRFValidationError(
            f'Максимум {_MAX_SLIDES_PER_STORE} слайдов на магазин. '
            f'Сейчас: {current_count}.'
        )

    slide = Slide.objects.create(store=locked_store, **slide_fields)

    logger.info(
        'slide_created store=%s slide=%s total=%d',
        locked_store.uuid, slide.pk, current_count + 1,
    )
    return slide


@transaction.atomic
def reorder_slides(store: Store, order_map: dict[int, int]) -> int:
    """
    A-5 REFACTOR: extracted from StoreSlideSetOrderingView.post().

    Applies sort_order values to Slide rows belonging to `store` in one
    atomic bulk_update. Slides not owned by this store are silently ignored
    (the filter provides ownership enforcement).

    Args:
        store:     Store instance (ownership already verified by the caller).
        order_map: dict mapping slide_pk (int) → new sort_order (int).
                   Only slide PKs present in this dict are updated.

    Returns:
        Number of slides actually updated.
    """
    from apps.stores.models import Slide

    slides = list(Slide.objects.filter(pk__in=order_map.keys(), store=store))
    for slide in slides:
        slide.sort_order = order_map[slide.pk]
    if slides:
        Slide.objects.bulk_update(slides, ['sort_order'])

    logger.info(
        'slides_reordered store=%s count=%d',
        store.uuid, len(slides),
    )
    return len(slides)
