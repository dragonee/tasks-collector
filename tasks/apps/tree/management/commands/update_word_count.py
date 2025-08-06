from django.core.management.base import BaseCommand
from ...utils.statistics import update_word_count_statistic, update_all_word_count_statistics


class Command(BaseCommand):
    help = 'Update word count statistics for all events and all years'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            help='Calculate word count for a specific year only'
        )

    def handle(self, *args, **options):
        year = options.get('year')
        
        if year:
            # Update specific year only
            self.stdout.write(f'Calculating word count for {year}...')
            total_words = update_word_count_statistic(year=year)
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully updated word count for {year}: {total_words:,} words'
                )
            )
        else:
            # Update all years and overall total
            self.stdout.write('Calculating word count for all events and all years...')
            
            results = update_all_word_count_statistics()
            
            # Display overall total
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully updated total word count: {results["total"]:,} words'
                )
            )
            
            # Display each year
            years = list(results['years'].keys())
            self.stdout.write(f'Found {len(years)} years in database: {sorted(years)}')
            
            for year in sorted(years):
                year_words = results['years'][year]
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully updated word count for {year}: {year_words:,} words'
                    )
                )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Completed updating word counts for all {len(years)} years plus overall total'
                )
            )