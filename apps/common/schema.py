"""
Custom AutoSchema that automatically tags endpoints by Django app.
Provides clean grouping in Swagger UI without decorating every view.
"""
from drf_spectacular.openapi import AutoSchema

# Map from Python module fragment → Swagger tag name
_APP_TAG_MAP = {
    'apps.accounts':      'Accounts',
    'apps.stores':        'Stores',
    'apps.products':      'Products',
    'apps.orders':        'Orders',
    'apps.employees':     'Employees',
    'apps.notifications': 'Notifications',
    'apps.countryapi':    'CountryAPI',
}


class TaggedAutoSchema(AutoSchema):
    """
    Derives Swagger tag from the view's module path.
    Views can still override by setting a class-level `swagger_tags` list.

    Usage:
        class MyView(APIView):
            swagger_tags = ['Custom Tag']   # optional override
    """

    def get_tags(self):
        # 1. Explicit per-view override
        if hasattr(self.view, 'swagger_tags'):
            return list(self.view.swagger_tags)

        # 2. Derive from module path
        module: str = self.view.__class__.__module__
        for module_fragment, tag_name in _APP_TAG_MAP.items():
            if module.startswith(module_fragment):
                return [tag_name]

        # 3. Fall back to drf-spectacular default
        return super().get_tags()
