from django.core.management.base import BaseCommand
from apps.countryapi.models import Country, Region, City

GEO_DATA = {
    'Кыргызстан': {
        'code': 'KG',
        'regions': {
            'Чуйская область': ['Бишкек', 'Токмок', 'Кант', 'Кара-Балта', 'Сокулук'],
            'Ошская область': ['Ош', 'Узген', 'Кара-Суу', 'Ноокат'],
            'Джалал-Абадская область': ['Джалал-Абад', 'Таш-Кумыр', 'Кочкор-Ата', 'Майлуу-Суу'],
            'Баткенская область': ['Баткен', 'Кадамжай', 'Сулюкта'],
            'Нарынская область': ['Нарын', 'Ат-Башы', 'Кочкор'],
            'Иссык-Кульская область': ['Каракол', 'Балыкчы', 'Чолпон-Ата', 'Бостери'],
            'Таласская область': ['Талас', 'Кара-Буура'],
        },
    },
    'Казахстан': {
        'code': 'KZ',
        'regions': {
            'Алматинская область': ['Алматы', 'Талдыкорган', 'Капшагай', 'Конаев'],
            'Нур-Султан (Астана)': ['Астана'],
            'Карагандинская область': ['Караганда', 'Темиртау', 'Балхаш'],
            'Шымкент': ['Шымкент'],
        },
    },
    'Россия': {
        'code': 'RU',
        'regions': {
            'Москва': ['Москва'],
            'Санкт-Петербург': ['Санкт-Петербург'],
            'Новосибирская область': ['Новосибирск'],
        },
    },
    'Узбекистан': {
        'code': 'UZ',
        'regions': {
            'Ташкент': ['Ташкент'],
            'Самаркандская область': ['Самарканд'],
            'Ферганская область': ['Фергана', 'Маргилан'],
        },
    },
}


class Command(BaseCommand):
    help = 'Seed initial geo data: countries, regions, cities'

    def handle(self, *args, **options):
        created_countries = 0
        created_regions = 0
        created_cities = 0

        for country_name, country_data in GEO_DATA.items():
            country, c_created = Country.objects.get_or_create(
                name=country_name,
                defaults={'code': country_data['code']},
            )
            if c_created:
                created_countries += 1
                self.stdout.write(f'  + Страна: {country_name}')

            for region_name, cities in country_data['regions'].items():
                region, r_created = Region.objects.get_or_create(
                    country=country,
                    name=region_name,
                )
                if r_created:
                    created_regions += 1

                for city_name in cities:
                    _, ci_created = City.objects.get_or_create(
                        region=region,
                        name=city_name,
                    )
                    if ci_created:
                        created_cities += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nГотово! Создано: '
            f'{created_countries} стран, '
            f'{created_regions} регионов, '
            f'{created_cities} городов.'
        ))
