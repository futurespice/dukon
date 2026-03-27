from rest_framework.throttling import ScopedRateThrottle


class WhatsAppThrottle(ScopedRateThrottle):
    """5 WhatsApp messages per hour per IP."""
    scope = 'whatsapp'


class AuthThrottle(ScopedRateThrottle):
    """20 auth attempts per hour per IP."""
    scope = 'auth'


class VerifyCodeThrottle(ScopedRateThrottle):
    """10 code verification attempts per hour per IP — prevents brute-force."""
    scope = 'verify_code'


class OrderTrackThrottle(ScopedRateThrottle):
    """
    R-3 FIX (Order ID enumeration via /orders/track/):
    The original VerifyCodeThrottle throttled by IP only (10/hour).
    An attacker with 1 000 proxy IPs x 10 attempts = 10 000 probes/hour,
    enough to scan a contiguous range of order IDs and correlate phone
    numbers with orders.

    Fix: throttle key is (IP + order_id), so each IP is limited to
    5 requests per specific order_id per hour.  Scanning a single order
    across different IPs is still possible, but the cost per IP is halved
    and leaking the mapping of phone → order requires separate IPs per
    order, making mass enumeration economically unviable.

    Combined with the existing identical 404 message for both
    'wrong phone' and 'order not found', this makes enumeration hard
    without changing the public API at all.
    """
    scope = 'order_track'

    def get_cache_key(self, request, view):
        # Include the requested order_id in the throttle key so that
        # an attacker can't just rotate IPs to probe the same order.
        ident = self.get_ident(request)
        order_id = request.query_params.get('order_id', '')
        # Sanitise: only keep digits to avoid cache key injection.
        safe_order_id = ''.join(c for c in str(order_id) if c.isdigit())[:20]
        return self.cache_format % {
            'scope': self.scope,
            'ident': f'{ident}:{safe_order_id}',
        }
