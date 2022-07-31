from django.contrib import admin
from .models import Reward, RewardTableItem, Claim, Claimed


class RewardTableInline(admin.TabularInline):
    model = RewardTableItem
    fk_name = "table"


class RewardAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}

    list_display = ('__str__', 'slug', 'has_table',)

    inlines = [
        RewardTableInline
    ]

admin.site.register(Reward, RewardAdmin)
admin.site.register(Claim)
admin.site.register(Claimed)