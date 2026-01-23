"""Tests for transaction generation with seasonal and time-of-day multipliers.

Covers:
- Issue #9: Time-of-day patterns (phase_multipliers, active_hours)
- Issue #10: Seasonal multipliers (BUSINESS_SEASONALITY)
"""

from datetime import date
from decimal import Decimal

import pytest

from atlas_town.config.personas_loader import load_persona_day_patterns
from atlas_town.transactions import (
    BUSINESS_PATTERNS,
    BUSINESS_SEASONALITY,
    TransactionGenerator,
    TransactionPattern,
    TransactionType,
    get_business_day_patterns,
)


class TestBusinessSeasonality:
    """Tests for BUSINESS_SEASONALITY configuration."""

    def test_all_businesses_have_patterns(self):
        """All businesses with patterns should have seasonality defined."""
        for business_key in BUSINESS_PATTERNS:
            assert business_key in BUSINESS_SEASONALITY, (
                f"Missing seasonality for {business_key}"
            )

    def test_craig_has_dramatic_seasonal_variation(self):
        """Craig's landscaping should have ~10x variation (peak vs slow)."""
        craig = BUSINESS_SEASONALITY["craig"]

        # Peak months (June, July should be 2.0x)
        assert craig[6] == 2.0
        assert craig[7] == 2.0

        # Slow months (Jan should be 0.2x)
        assert craig[1] == 0.2

        # Ratio should be ~10x
        peak = max(craig.values())
        slow = min(craig.values())
        ratio = peak / slow
        assert ratio >= 8.0, f"Expected 10x variation, got {ratio:.1f}x"

    def test_marcus_peaks_in_spring_summer(self):
        """Marcus's realty should peak during home-buying season."""
        marcus = BUSINESS_SEASONALITY["marcus"]

        # Spring/summer peak
        assert marcus[6] == 2.0  # June is peak
        assert marcus[5] >= 1.5  # May is high
        assert marcus[4] >= 1.0  # April is elevated

        # Winter slow
        assert marcus[12] <= 0.5
        assert marcus[1] <= 0.5

    def test_tony_has_low_seasonality(self):
        """Tony's pizzeria should have minimal seasonal variation."""
        tony = BUSINESS_SEASONALITY["tony"]

        # Only slight holiday boost, no major swings
        values = tony.values()
        assert max(values) <= 1.2  # Max boost is small
        # All multipliers should be near 1.0
        for mult in values:
            assert 0.8 <= mult <= 1.5

    def test_seasonality_values_are_positive(self):
        """All seasonality multipliers should be positive."""
        for business_key, months in BUSINESS_SEASONALITY.items():
            for month, mult in months.items():
                assert 1 <= month <= 12, f"Invalid month {month} for {business_key}"
                assert mult > 0, f"Non-positive multiplier {mult} for {business_key}"


class TestGetSeasonalMultiplier:
    """Tests for TransactionGenerator._get_seasonal_multiplier()."""

    @pytest.fixture
    def generator(self):
        """Create a seeded generator for reproducibility."""
        return TransactionGenerator(seed=42)

    @pytest.fixture
    def base_pattern(self):
        """Basic pattern without seasonal overrides."""
        return TransactionPattern(
            transaction_type=TransactionType.INVOICE,
            description_template="Test service",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=0.5,
        )

    def test_returns_business_seasonality(self, generator, base_pattern):
        """Should return business-wide seasonality when pattern has none."""
        # Craig in June (peak) should return 2.0
        mult = generator._get_seasonal_multiplier("craig", 6, base_pattern)
        assert mult == 2.0

        # Craig in January (slow) should return 0.2
        mult = generator._get_seasonal_multiplier("craig", 1, base_pattern)
        assert mult == 0.2

    def test_returns_1_for_undefined_month(self, generator, base_pattern):
        """Should return 1.0 for months not in seasonality dict."""
        # Tony in March has no seasonality defined
        mult = generator._get_seasonal_multiplier("tony", 3, base_pattern)
        assert mult == 1.0

    def test_returns_1_for_unknown_business(self, generator, base_pattern):
        """Should return 1.0 for businesses not in BUSINESS_SEASONALITY."""
        mult = generator._get_seasonal_multiplier("unknown_biz", 6, base_pattern)
        assert mult == 1.0

    def test_pattern_override_takes_precedence(self, generator):
        """Pattern-specific seasonal_multipliers should override business-wide."""
        # Pattern with its own seasonal multiplier for June
        pattern_with_override = TransactionPattern(
            transaction_type=TransactionType.INVOICE,
            description_template="Special service",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=0.5,
            seasonal_multipliers={6: 0.5},  # Override: June is slow for this pattern
        )

        # Even though Craig's business-wide June is 2.0, pattern says 0.5
        mult = generator._get_seasonal_multiplier("craig", 6, pattern_with_override)
        assert mult == 0.5

    def test_pattern_falls_back_for_undefined_months(self, generator):
        """Pattern with partial seasonal_multipliers should fall back to business."""
        pattern_partial = TransactionPattern(
            transaction_type=TransactionType.INVOICE,
            description_template="Partial seasonal",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=0.5,
            seasonal_multipliers={6: 0.5},  # Only June defined
        )

        # June uses pattern override
        mult = generator._get_seasonal_multiplier("craig", 6, pattern_partial)
        assert mult == 0.5

        # January falls back to business-wide (0.2)
        mult = generator._get_seasonal_multiplier("craig", 1, pattern_partial)
        assert mult == 0.2


class TestShouldGenerateWithSeasonality:
    """Tests for _should_generate() with seasonal multipliers."""

    @pytest.fixture
    def generator(self):
        """Create a seeded generator for reproducibility."""
        return TransactionGenerator(seed=42)

    @pytest.fixture
    def high_prob_pattern(self):
        """Pattern with high base probability."""
        return TransactionPattern(
            transaction_type=TransactionType.INVOICE,
            description_template="Test",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=0.8,
        )

    def test_seasonal_multiplier_affects_probability(self, generator, high_prob_pattern):
        """Seasonal multiplier should affect generation probability."""
        # Run many iterations to verify statistical effect
        peak_date = date(2024, 6, 15)  # June (Craig peak = 2.0)
        slow_date = date(2024, 1, 15)  # January (Craig slow = 0.2)

        # Count generations over many trials
        peak_count = 0
        slow_count = 0
        trials = 1000

        for _ in range(trials):
            gen = TransactionGenerator(seed=None)  # Random for statistics
            if gen._should_generate(
                high_prob_pattern, peak_date, business_key="craig"
            ):
                peak_count += 1
            if gen._should_generate(
                high_prob_pattern, slow_date, business_key="craig"
            ):
                slow_count += 1

        # Peak should generate much more often (expect ~1.0 vs ~0.16 after clamping)
        # With prob=0.8, peak=2.0 → clamped to 1.0, slow=0.2 → 0.16
        # Ratio should be roughly 6x
        assert peak_count > slow_count * 3, (
            f"Peak ({peak_count}) should be much higher than slow ({slow_count})"
        )

    def test_backward_compatible_without_business_key(self, generator, high_prob_pattern):
        """Should work without business_key (backward compatibility)."""
        test_date = date(2024, 6, 15)

        # Should not raise, just doesn't apply seasonal multiplier
        result = generator._should_generate(high_prob_pattern, test_date)
        assert isinstance(result, bool)

    def test_weekend_and_seasonal_stack(self, generator):
        """Weekend boost, day multiplier, and seasonal multiplier should all apply."""
        pattern = TransactionPattern(
            transaction_type=TransactionType.CASH_SALE,
            description_template="Test",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=0.5,
            weekend_boost=1.5,
        )

        # Saturday in June for Craig (day=0.4, weekend=1.5, seasonal=2.0)
        # Effective: 0.5 * 0.4 * 1.5 * 2.0 = 0.6
        saturday_june = date(2024, 6, 15)  # This is a Saturday

        # Count over trials - should be moderately high
        count = sum(
            1
            for _ in range(500)
            if TransactionGenerator()._should_generate(
                pattern, saturday_june, business_key="craig"
            )
        )

        # Should generate moderately often (prob ~0.6)
        assert count > 220, f"Expected moderate generation rate (~0.6), got {count}/500"


class TestTransactionPatternSeasonalMultipliers:
    """Tests for seasonal_multipliers field on TransactionPattern."""

    def test_default_is_none(self):
        """seasonal_multipliers should default to None."""
        pattern = TransactionPattern(
            transaction_type=TransactionType.INVOICE,
            description_template="Test",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=0.5,
        )
        assert pattern.seasonal_multipliers is None

    def test_can_set_seasonal_multipliers(self):
        """Should accept seasonal_multipliers dict."""
        pattern = TransactionPattern(
            transaction_type=TransactionType.INVOICE,
            description_template="Holiday special",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=0.5,
            seasonal_multipliers={11: 2.0, 12: 2.5},
        )
        assert pattern.seasonal_multipliers == {11: 2.0, 12: 2.5}


class TestGenerateDailyTransactions:
    """Tests for generate_daily_transactions with seasonal multipliers."""

    @pytest.fixture
    def generator(self):
        return TransactionGenerator(seed=42)

    @pytest.fixture
    def mock_customers(self):
        return [
            {"id": "11111111-1111-1111-1111-111111111111", "name": "Test Customer"},
        ]

    @pytest.fixture
    def mock_vendors(self):
        return [
            {"id": "22222222-2222-2222-2222-222222222222", "name": "Test Vendor"},
        ]

    def test_peak_season_generates_more_transactions(
        self, mock_customers, mock_vendors
    ):
        """Craig should generate more transactions in peak season."""
        # Use Wednesdays to compare seasonal effect fairly
        # (Craig's day multiplier is 1.2 for Wednesday in both cases)
        peak_date = date(2024, 6, 19)  # Wednesday in June (seasonal=2.0, day=1.2)
        slow_date = date(2024, 1, 17)  # Wednesday in January (seasonal=0.2, day=1.2)

        # Run multiple trials and count total transactions
        peak_total = 0
        slow_total = 0
        trials = 100

        for i in range(trials):
            gen = TransactionGenerator(seed=i)
            peak_txns = gen.generate_daily_transactions(
                "craig", peak_date, mock_customers, mock_vendors
            )
            slow_txns = gen.generate_daily_transactions(
                "craig", slow_date, mock_customers, mock_vendors
            )
            peak_total += len(peak_txns)
            slow_total += len(slow_txns)

        # Peak should generate significantly more (expect ~5-10x ratio due to seasonal)
        assert peak_total > slow_total * 3, (
            f"Peak ({peak_total}) should be much higher than slow ({slow_total})"
        )


# ============================================================================
# Issue #9: Time-of-Day Patterns (phase_multipliers, active_hours)
# ============================================================================


class TestTransactionPatternTimeOfDay:
    """Tests for phase_multipliers and active_hours fields on TransactionPattern."""

    def test_phase_multipliers_default_is_none(self):
        """phase_multipliers should default to None."""
        pattern = TransactionPattern(
            transaction_type=TransactionType.CASH_SALE,
            description_template="Test",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=0.5,
        )
        assert pattern.phase_multipliers is None

    def test_active_hours_default_is_none(self):
        """active_hours should default to None."""
        pattern = TransactionPattern(
            transaction_type=TransactionType.CASH_SALE,
            description_template="Test",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=0.5,
        )
        assert pattern.active_hours is None

    def test_can_set_phase_multipliers(self):
        """Should accept phase_multipliers dict."""
        pattern = TransactionPattern(
            transaction_type=TransactionType.CASH_SALE,
            description_template="Dinner rush",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=0.5,
            phase_multipliers={"evening": 2.5, "night": 1.5},
        )
        assert pattern.phase_multipliers == {"evening": 2.5, "night": 1.5}

    def test_can_set_active_hours(self):
        """Should accept active_hours tuple."""
        pattern = TransactionPattern(
            transaction_type=TransactionType.CASH_SALE,
            description_template="Lunch service",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=0.5,
            active_hours=(11, 14),  # 11 AM - 2 PM
        )
        assert pattern.active_hours == (11, 14)


class TestActiveHoursFiltering:
    """Tests for active_hours time filtering in _should_generate()."""

    @pytest.fixture
    def generator(self):
        return TransactionGenerator(seed=42)

    @pytest.fixture
    def lunch_pattern(self):
        """Pattern active only during lunch hours (11 AM - 2 PM)."""
        return TransactionPattern(
            transaction_type=TransactionType.CASH_SALE,
            description_template="Lunch service",
            min_amount=Decimal("400"),
            max_amount=Decimal("1200"),
            probability=1.0,  # High prob to make filtering obvious
            active_hours=(11, 14),
        )

    def test_generates_during_active_hours(self, generator, lunch_pattern):
        """Should generate during active hours."""
        test_date = date(2024, 6, 17)  # Monday

        # 12 PM is within 11-14 range
        result = generator._should_generate(lunch_pattern, test_date, current_hour=12)
        # With prob=1.0 and no modifiers, should always be True
        assert result is True

    def test_skips_outside_active_hours(self, generator, lunch_pattern):
        """Should not generate outside active hours."""
        test_date = date(2024, 6, 17)

        # 9 AM is before 11 AM start
        result = generator._should_generate(lunch_pattern, test_date, current_hour=9)
        assert result is False

        # 3 PM (15) is after 2 PM (14) end
        result = generator._should_generate(lunch_pattern, test_date, current_hour=15)
        assert result is False

    def test_active_hours_boundary_start(self, generator, lunch_pattern):
        """Should generate at the start hour (inclusive)."""
        test_date = date(2024, 6, 17)
        result = generator._should_generate(lunch_pattern, test_date, current_hour=11)
        assert result is True

    def test_active_hours_boundary_end(self, generator, lunch_pattern):
        """Should not generate at the end hour (exclusive)."""
        test_date = date(2024, 6, 17)
        result = generator._should_generate(lunch_pattern, test_date, current_hour=14)
        assert result is False

    def test_no_filtering_without_current_hour(self, generator, lunch_pattern):
        """Without current_hour, active_hours check is skipped."""
        test_date = date(2024, 6, 17)

        # When current_hour is None, active_hours constraint doesn't apply
        result = generator._should_generate(lunch_pattern, test_date, current_hour=None)
        # Should just use base probability (1.0), so True
        assert result is True


class TestActiveHoursMidnightWrap:
    """Tests for active_hours that wrap around midnight."""

    @pytest.fixture
    def generator(self):
        return TransactionGenerator(seed=42)

    @pytest.fixture
    def late_night_pattern(self):
        """Pattern active late night wrapping past midnight (20-2)."""
        return TransactionPattern(
            transaction_type=TransactionType.CASH_SALE,
            description_template="Late night service",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=1.0,
            active_hours=(20, 2),  # 8 PM to 2 AM (wraps midnight)
        )

    def test_generates_before_midnight(self, generator, late_night_pattern):
        """Should generate before midnight in wrap range."""
        test_date = date(2024, 6, 17)

        # 10 PM (22) is in 20-2 range
        result = generator._should_generate(late_night_pattern, test_date, current_hour=22)
        assert result is True

    def test_generates_after_midnight(self, generator, late_night_pattern):
        """Should generate after midnight in wrap range."""
        test_date = date(2024, 6, 17)

        # 1 AM is in 20-2 range (after midnight)
        result = generator._should_generate(late_night_pattern, test_date, current_hour=1)
        assert result is True

    def test_skips_during_day(self, generator, late_night_pattern):
        """Should not generate during day hours."""
        test_date = date(2024, 6, 17)

        # 10 AM is outside 20-2 range
        result = generator._should_generate(late_night_pattern, test_date, current_hour=10)
        assert result is False

        # 6 PM (18) is outside 20-2 range
        result = generator._should_generate(late_night_pattern, test_date, current_hour=18)
        assert result is False


class TestPhaseMultipliers:
    """Tests for phase_multipliers in _should_generate()."""

    @pytest.fixture
    def generator(self):
        return TransactionGenerator(seed=42)

    @pytest.fixture
    def dinner_rush_pattern(self):
        """Pattern with evening phase boost."""
        return TransactionPattern(
            transaction_type=TransactionType.CASH_SALE,
            description_template="Dinner rush",
            min_amount=Decimal("1200"),
            max_amount=Decimal("3500"),
            probability=0.4,
            phase_multipliers={"evening": 2.5, "night": 1.5},
        )

    def test_phase_multiplier_boosts_probability(self, dinner_rush_pattern):
        """Phase multiplier should increase generation rate."""
        test_date = date(2024, 6, 17)

        # Count generations with and without evening phase
        evening_count = 0
        no_phase_count = 0
        trials = 500

        for _ in range(trials):
            gen = TransactionGenerator()
            if gen._should_generate(
                dinner_rush_pattern, test_date, current_phase="evening"
            ):
                evening_count += 1
            if gen._should_generate(
                dinner_rush_pattern, test_date, current_phase=None
            ):
                no_phase_count += 1

        # Evening (0.4 * 2.5 = 1.0) should generate much more than base (0.4)
        assert evening_count > no_phase_count * 1.5, (
            f"Evening ({evening_count}) should be higher than no phase ({no_phase_count})"
        )

    def test_undefined_phase_uses_default(self, generator, dinner_rush_pattern):
        """Undefined phase should use multiplier of 1.0."""
        test_date = date(2024, 6, 17)

        # "morning" is not in phase_multipliers, should use 1.0
        morning_count = sum(
            1
            for _ in range(300)
            if TransactionGenerator()._should_generate(
                dinner_rush_pattern, test_date, current_phase="morning"
            )
        )

        # Should be around base probability (0.4) ≈ 120/300
        assert 80 < morning_count < 180, f"Expected ~120, got {morning_count}"

    def test_phase_and_weekend_stack(self, generator):
        """Phase multiplier and weekend boost should both apply (no business_key)."""
        pattern = TransactionPattern(
            transaction_type=TransactionType.CASH_SALE,
            description_template="Weekend dinner",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=0.3,
            weekend_boost=1.5,
            phase_multipliers={"evening": 2.0},
        )

        # Saturday evening without business_key: 0.3 * 1.5 * 2.0 = 0.9
        # (no day multiplier applied without business_key)
        saturday = date(2024, 6, 15)  # Saturday

        count = sum(
            1
            for _ in range(500)
            if TransactionGenerator()._should_generate(
                pattern, saturday, current_phase="evening"
            )
        )

        # Should generate very often (prob ~0.9)
        assert count > 350, f"Expected high rate (~0.9), got {count}/500"


class TestTonyTimeAwarePatterns:
    """Tests for Tony's pizzeria time-aware transaction patterns (Issue #9)."""

    def test_tony_has_lunch_pattern(self):
        """Tony should have a lunch service pattern."""
        tony_patterns = BUSINESS_PATTERNS.get("tony", [])
        lunch_patterns = [
            p for p in tony_patterns
            if "lunch" in p.description_template.lower()
        ]
        assert len(lunch_patterns) >= 1, "Tony should have lunch pattern"

        lunch = lunch_patterns[0]
        assert lunch.active_hours is not None
        assert lunch.active_hours[0] >= 10  # Starts around lunch time
        assert lunch.active_hours[1] <= 15  # Ends by mid-afternoon

    def test_tony_has_dinner_rush_pattern(self):
        """Tony should have a dinner rush pattern with evening boost."""
        tony_patterns = BUSINESS_PATTERNS.get("tony", [])
        dinner_patterns = [
            p for p in tony_patterns
            if "dinner" in p.description_template.lower()
        ]
        assert len(dinner_patterns) >= 1, "Tony should have dinner pattern"

        dinner = dinner_patterns[0]
        assert dinner.phase_multipliers is not None
        assert "evening" in dinner.phase_multipliers
        assert dinner.phase_multipliers["evening"] >= 2.0  # Significant boost

    def test_tony_has_late_night_pattern(self):
        """Tony should have a late-night pattern."""
        tony_patterns = BUSINESS_PATTERNS.get("tony", [])
        late_patterns = [
            p for p in tony_patterns
            if "late" in p.description_template.lower() or "night" in p.description_template.lower()
        ]
        assert len(late_patterns) >= 1, "Tony should have late night pattern"

        late = late_patterns[0]
        # Late night should have higher weekend boost
        assert late.weekend_boost >= 1.5

    def test_tony_dinner_rush_highest_value(self):
        """Dinner rush should have highest transaction values."""
        tony_patterns = BUSINESS_PATTERNS.get("tony", [])

        # Find cash sale patterns
        cash_sales = [
            p for p in tony_patterns
            if p.transaction_type == TransactionType.CASH_SALE
        ]

        # Dinner pattern should have highest max_amount among cash sales
        dinner_patterns = [p for p in cash_sales if "dinner" in p.description_template.lower()]
        other_cash_sales = [p for p in cash_sales if "dinner" not in p.description_template.lower()]

        if dinner_patterns and other_cash_sales:
            dinner_max = max(p.max_amount for p in dinner_patterns)
            other_max = max(p.max_amount for p in other_cash_sales)
            assert dinner_max >= other_max, "Dinner should have highest value"


class TestAllMultipliersStack:
    """Test that all multipliers (day, weekend, phase, seasonal) stack correctly."""

    def test_all_four_multipliers_stack(self):
        """Day, weekend boost, phase multiplier, and seasonal should all apply."""
        pattern = TransactionPattern(
            transaction_type=TransactionType.CASH_SALE,
            description_template="Peak everything",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=0.1,  # Low base probability
            weekend_boost=1.5,
            phase_multipliers={"evening": 2.0},
        )

        # Saturday in June for Craig:
        # 0.1 (base) * 0.4 (day=Sat) * 1.5 (weekend) * 2.0 (phase) * 2.0 (seasonal) = 0.24
        saturday_june = date(2024, 6, 15)

        count = sum(
            1
            for _ in range(1000)
            if TransactionGenerator()._should_generate(
                pattern, saturday_june,
                current_phase="evening",
                business_key="craig",
            )
        )

        # Should be around 24% generation rate
        assert 150 < count < 350, f"Expected ~240 (0.24 rate), got {count}/1000"

    def test_weekday_no_phase_slow_season(self):
        """Weekday without phase in slow season should have very low rate."""
        pattern = TransactionPattern(
            transaction_type=TransactionType.INVOICE,
            description_template="Test",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=0.5,
            phase_multipliers={"evening": 2.0},  # But we won't use evening
        )

        # Monday in January for Craig (slow season = 0.2, day = 0.9)
        # 0.5 (base) * 0.9 (day) * 1.0 (weekday boost) * 1.0 (no phase match) * 0.2 (seasonal) = 0.09
        monday_january = date(2024, 1, 15)

        count = sum(
            1
            for _ in range(1000)
            if TransactionGenerator()._should_generate(
                pattern, monday_january,
                current_phase="morning",  # Not in phase_multipliers
                business_key="craig",
            )
        )

        # Should be around 9% generation rate
        assert 30 < count < 180, f"Expected ~90 (0.09 rate), got {count}/1000"


# ============================================================================
# Issue #11: Day-of-Week Patterns (persona YAML)
# ============================================================================


class TestBusinessDayPatterns:
    """Tests for day-of-week patterns loaded from persona YAML."""

    def test_all_businesses_have_day_patterns(self):
        """All businesses with patterns should have day-of-week patterns defined."""
        patterns = load_persona_day_patterns()
        for business_key in BUSINESS_PATTERNS:
            assert business_key in patterns, (
                f"Missing day patterns for {business_key}"
            )
            assert len(patterns[business_key]) == 7, (
                f"Expected 7 day entries for {business_key}"
            )

    def test_tony_peaks_thu_sat(self):
        """Tony's pizzeria should peak Thursday-Saturday."""
        tony = get_business_day_patterns()["tony"]

        # Peak days (Thu=3, Fri=4, Sat=5)
        assert tony[3] >= 1.2  # Thursday
        assert tony[4] >= 1.2  # Friday
        assert tony[5] >= 1.4  # Saturday (highest)

        # Slower early week
        assert tony[0] < 1.0  # Monday
        assert tony[1] < 1.0  # Tuesday

        # Saturday should be the peak
        assert tony[5] == max(tony.values())

    def test_chen_quiet_on_weekends(self):
        """Chen's dental practice should be quiet on weekends."""
        chen = get_business_day_patterns()["chen"]

        # Weekdays are normal to busy
        assert chen[1] >= 1.0  # Tuesday
        assert chen[2] >= 1.0  # Wednesday
        assert chen[3] >= 1.0  # Thursday

        # Weekends are very slow/closed
        assert chen[5] <= 0.5  # Saturday (limited hours)
        assert chen[6] == 0.0  # Sunday (closed)

    def test_craig_landscaping_weekday_focus(self):
        """Craig's landscaping should focus on weekdays, slow on weekends."""
        craig = get_business_day_patterns()["craig"]

        # Mid-week peak
        assert craig[2] >= 1.1  # Wednesday (peak)

        # Weekends slow
        assert craig[5] <= 0.5  # Saturday
        assert craig[6] <= 0.5  # Sunday

    def test_maya_tech_consulting_pattern(self):
        """Maya's tech consulting should be busy Mon-Thu, quiet on weekends."""
        maya = get_business_day_patterns()["maya"]

        # Business days busy
        assert maya[0] >= 1.0  # Monday
        assert maya[1] >= 1.0  # Tuesday
        assert maya[2] >= 1.0  # Wednesday
        assert maya[3] >= 1.0  # Thursday

        # Friday lighter, weekends very quiet
        assert maya[4] < 1.0  # Friday
        assert maya[5] <= 0.3  # Saturday
        assert maya[6] <= 0.2  # Sunday

    def test_marcus_weekend_showings(self):
        """Marcus's real estate should have weekend showings."""
        marcus = get_business_day_patterns()["marcus"]

        # Weekend showings should be busy
        assert marcus[5] >= 1.3  # Saturday
        assert marcus[6] >= 1.0  # Sunday

        # Thu-Fri closings
        assert marcus[3] >= 1.0  # Thursday
        assert marcus[4] >= 1.0  # Friday

    def test_day_patterns_values_valid(self):
        """All day pattern multipliers should be valid (non-negative)."""
        for business_key, days in get_business_day_patterns().items():
            for day, mult in days.items():
                assert 0 <= day <= 6, f"Invalid day {day} for {business_key}"
                assert mult >= 0, f"Negative multiplier {mult} for {business_key} day {day}"


class TestGetDayMultiplier:
    """Tests for TransactionGenerator._get_day_multiplier()."""

    @pytest.fixture
    def generator(self):
        """Create a seeded generator for reproducibility."""
        return TransactionGenerator(seed=42)

    def test_returns_business_day_multiplier(self, generator):
        """Should return correct day multiplier for known business/day."""
        # Tony on Saturday (peak)
        mult = generator._get_day_multiplier("tony", 5)
        assert mult == 1.5

        # Tony on Monday (slow)
        mult = generator._get_day_multiplier("tony", 0)
        assert mult == 0.7

    def test_returns_1_for_undefined_day(self, generator):
        """Should return 1.0 for days not in day patterns dict."""
        # If a business has a partial dict (all have full, but test the logic)
        # Use an unknown business which returns empty dict
        mult = generator._get_day_multiplier("unknown_biz", 0)
        assert mult == 1.0

    def test_returns_1_for_unknown_business(self, generator):
        """Should return 1.0 for businesses not in day patterns."""
        mult = generator._get_day_multiplier("unknown_biz", 5)
        assert mult == 1.0

    def test_chen_sunday_returns_zero(self, generator):
        """Chen on Sunday should return 0.0 (closed)."""
        mult = generator._get_day_multiplier("chen", 6)
        assert mult == 0.0


class TestShouldGenerateWithDayPatterns:
    """Tests for _should_generate() with day-of-week multipliers."""

    @pytest.fixture
    def high_prob_pattern(self):
        """Pattern with high base probability."""
        return TransactionPattern(
            transaction_type=TransactionType.INVOICE,
            description_template="Test",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=0.8,
        )

    def test_day_multiplier_affects_probability(self, high_prob_pattern):
        """Day multiplier should affect generation probability."""
        # Tony on Saturday (mult=1.5) vs Monday (mult=0.7)
        saturday = date(2024, 6, 15)  # Saturday
        monday = date(2024, 6, 17)    # Monday

        sat_count = 0
        mon_count = 0
        trials = 1000

        for _ in range(trials):
            gen = TransactionGenerator(seed=None)
            if gen._should_generate(high_prob_pattern, saturday, business_key="tony"):
                sat_count += 1
            if gen._should_generate(high_prob_pattern, monday, business_key="tony"):
                mon_count += 1

        # Saturday should generate more often (1.5x vs 0.7x)
        # Expected ratio: ~2.1x (1.5/0.7)
        assert sat_count > mon_count * 1.5, (
            f"Saturday ({sat_count}) should be much higher than Monday ({mon_count})"
        )

    def test_chen_sunday_generates_nothing(self, high_prob_pattern):
        """Chen on Sunday (mult=0.0) should never generate."""
        sunday = date(2024, 6, 16)  # Sunday

        count = sum(
            1
            for _ in range(500)
            if TransactionGenerator()._should_generate(
                high_prob_pattern, sunday, business_key="chen"
            )
        )

        # Should be exactly 0 (0.0 multiplier)
        assert count == 0, f"Expected 0 generations on Sunday for Chen, got {count}"

    def test_backward_compatible_without_business_key(self, high_prob_pattern):
        """Should work without business_key (backward compatibility)."""
        test_date = date(2024, 6, 15)

        # Should not raise, just doesn't apply day multiplier
        result = TransactionGenerator(seed=42)._should_generate(
            high_prob_pattern, test_date
        )
        assert isinstance(result, bool)


class TestDayAndOtherMultipliersStack:
    """Test that day multipliers stack correctly with other multipliers."""

    def test_day_and_weekend_boost_stack(self):
        """Day multiplier and weekend boost should both apply."""
        pattern = TransactionPattern(
            transaction_type=TransactionType.CASH_SALE,
            description_template="Test",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=0.4,
            weekend_boost=1.5,
        )

        # Saturday for Tony: 0.4 * 1.5 (day) * 1.5 (weekend) = 0.9
        saturday = date(2024, 6, 15)

        count = sum(
            1
            for _ in range(500)
            if TransactionGenerator()._should_generate(
                pattern, saturday, business_key="tony"
            )
        )

        # Should be around 90% generation rate
        assert count > 350, f"Expected high rate (~0.9), got {count}/500"

    def test_day_and_seasonal_stack(self):
        """Day multiplier and seasonal multiplier should both apply."""
        pattern = TransactionPattern(
            transaction_type=TransactionType.INVOICE,
            description_template="Test",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=0.5,
        )

        # Wednesday in June for Craig:
        # day=1.2, seasonal=2.0 → 0.5 * 1.2 * 2.0 = 1.2 (clamped to ~1.0)
        wednesday_june = date(2024, 6, 19)  # Wednesday

        count = sum(
            1
            for _ in range(500)
            if TransactionGenerator()._should_generate(
                pattern, wednesday_june, business_key="craig"
            )
        )

        # Should be very high (prob > 1.0 after multipliers)
        assert count > 450, f"Expected very high rate, got {count}/500"

    def test_all_four_multipliers_stack(self):
        """Day, weekend, phase, and seasonal multipliers should all apply."""
        pattern = TransactionPattern(
            transaction_type=TransactionType.CASH_SALE,
            description_template="Peak everything",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=0.1,  # Low base probability
            weekend_boost=1.3,
            phase_multipliers={"evening": 1.5},
        )

        # Saturday in June for Tony during evening:
        # 0.1 (base) * 1.5 (day=Sat) * 1.3 (weekend) * 1.5 (phase) * 1.1 (seasonal Nov boost, but June=default 1.0)
        # Tony in June has no seasonal, so just: 0.1 * 1.5 * 1.3 * 1.5 ≈ 0.29
        saturday_june = date(2024, 6, 15)

        count = sum(
            1
            for _ in range(1000)
            if TransactionGenerator()._should_generate(
                pattern, saturday_june,
                current_phase="evening",
                business_key="tony",
            )
        )

        # Should be around 29% generation rate
        assert 180 < count < 400, f"Expected ~290 (0.29 rate), got {count}/1000"

    def test_low_day_multiplier_reduces_generation(self):
        """Low day multiplier should significantly reduce generation."""
        pattern = TransactionPattern(
            transaction_type=TransactionType.INVOICE,
            description_template="Test",
            min_amount=Decimal("100"),
            max_amount=Decimal("500"),
            probability=0.8,
        )

        # Sunday for Maya (mult=0.1)
        sunday = date(2024, 6, 16)

        count = sum(
            1
            for _ in range(1000)
            if TransactionGenerator()._should_generate(
                pattern, sunday, business_key="maya"
            )
        )

        # Should be around 8% (0.8 * 0.1)
        assert count < 150, f"Expected low rate (~0.08), got {count}/1000"
