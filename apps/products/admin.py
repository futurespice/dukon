from django.contrib import admin

from apps.products.models import Photo, Category, Product, ProductModel, ProductPhoto, FavoriteProduct


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'is_public', 'created_at')
    search_fields = ('name', 'alt_text')
    list_filter = ('is_public',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'store', 'parent', 'order', 'is_hidden')
    list_filter = ('is_hidden',)
    search_fields = ('name',)
    raw_id_fields = ('store', 'parent')
    list_editable = ('order', 'is_hidden')
    # AUDIT N+1 FIX: 'store' and 'parent' appear in list_display — without
    # list_select_related Django issues a separate SELECT for each FK per row.
    list_select_related = ('store', 'parent')


class ProductModelInline(admin.TabularInline):
    model = ProductModel
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'store', 'category', 'is_popular', 'is_hidden', 'is_stop', 'created_at')
    list_filter = ('is_popular', 'is_hidden', 'is_stop', 'is_for_children', 'is_vegan')
    search_fields = ('name', 'article', 'short_description')
    raw_id_fields = ('store', 'category')
    readonly_fields = ('created_at', 'updated_at', 'viewers')
    inlines = [ProductModelInline]
    # AUDIT N+1 FIX: 'store' and 'category' appear in list_display.
    list_select_related = ('store', 'category')

    def get_queryset(self, request):
        # AUDIT N+1 FIX: prefetch models so ProductModelInline doesn't issue
        # extra queries when opening the product detail page.
        qs = super().get_queryset(request)
        return qs.prefetch_related('models')


@admin.register(ProductModel)
class ProductModelAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'product', 'price', 'quantity')
    search_fields = ('name', 'product__name')
    raw_id_fields = ('product',)
    # AUDIT N+1 FIX: 'product' appears in list_display.
    list_select_related = ('product',)


@admin.register(ProductPhoto)
class ProductPhotoAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'image')
    raw_id_fields = ('product', 'image')
    # AUDIT N+1 FIX: 'product' and 'image' appear in list_display.
    list_select_related = ('product', 'image')


@admin.register(FavoriteProduct)
class FavoriteProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'product', 'created_at')
    raw_id_fields = ('user', 'product')
    # AUDIT N+1 FIX: 'user' and 'product' appear in list_display.
    list_select_related = ('user', 'product')
