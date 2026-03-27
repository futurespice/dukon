from django.urls import path
from apps.accounts import views

urlpatterns = [
    # ---- Auth ----
    path('register/', views.RegisterView.as_view(), name='accounts-register'),
    path('login/', views.LoginView.as_view(), name='accounts-login'),
    path('logout/', views.LogoutView.as_view(), name='accounts-logout'),
    # ---- Profile ----
    path('profile/', views.ProfileView.as_view(), name='accounts-profile'),
    path('profile/image/', views.ProfileImageView.as_view(), name='accounts-profile-image'),

    # ---- Change password (authenticated) ----
    path('change-password/', views.ChangePasswordView.as_view(), name='accounts-change-password'),

    # ---- Reset password via WhatsApp ----
    path(
        'reset-password/send-code/',
        views.ResetPasswordSendCodeView.as_view(),
        name='accounts-reset-password-send-code',
    ),
    path(
        'reset-password/confirm/',
        views.ResetPasswordConfirmView.as_view(),
        name='accounts-reset-password-confirm',
    ),

    # ---- Verify registration code (issues JWT on success) ----
    path(
        'check/verify-code/',
        views.CheckVerifyCodeView.as_view(),
        name='accounts-check-verify-code',
    ),

    # ---- Resend registration code via WhatsApp ----
    path(
        'resend-verify-code/',
        views.ResendVerifyCodeView.as_view(),
        name='accounts-resend-verify-code',
    ),

    # ---- Phone number change ----
    path(
        'phone-number-change/',
        views.PhoneNumberChangeView.as_view(),
        name='accounts-phone-change',
    ),
    path(
        'phone-number-change/confirm/',
        views.PhoneChangeConfirmView.as_view(),
        name='accounts-phone-change-confirm',
    ),

    # ---- Two-Factor Authentication via WhatsApp ----
    path('login/2fa/confirm/', views.TwoFAConfirmView.as_view(), name='accounts-2fa-confirm'),
    path('login/2fa/resend/', views.TwoFAResendView.as_view(), name='accounts-2fa-resend'),

    # ---- 2FA enable / disable (require password confirmation) ----
    path('2fa/enable/', views.TwoFAEnableView.as_view(), name='accounts-2fa-enable'),
    path('2fa/disable/', views.TwoFADisableView.as_view(), name='accounts-2fa-disable'),
]
