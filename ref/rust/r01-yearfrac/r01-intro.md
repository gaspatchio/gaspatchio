Excel’s YEARFRAC Function – Technical Breakdown for Rust (Polars) Implementation

Overview of Excel’s YEARFRAC

The YEARFRAC function in Excel returns a decimal fraction representing the number of years between two dates ￼. In other words, it calculates the proportion of a full year that spans between a start date and an end date. This is useful in financial calculations (e.g. accruing interest or calculating age in years with decimals). The syntax is YEARFRAC(start_date, end_date, [basis]), where start_date and end_date are the two dates, and basis is an optional integer (0–4) selecting the day-count convention ￼ ￼. If basis is omitted, it defaults to 0 (US 30/360). The result is a Double (floating-point) representing years (e.g. 1.5 would indicate one and a half years) ￼.

Notably, Excel’s YEARFRAC considers the absolute difference between the dates – swapping the order of start_date and end_date yields the same positive fraction ￼. In other words, Excel does not produce negative results for a reversed date order; it effectively uses the absolute number of days between the dates. (If a negative result is needed, one must manually apply a sign or swap the arguments outside YEARFRAC.)

Day Count Basis: The basis parameter specifies which day count convention to use in converting the day difference into a year fraction ￼:
	•	0 or omitted: US (NASD) 30/360
	•	1: Actual/Actual
	•	2: Actual/360
	•	3: Actual/365
	•	4: European 30/360

Each basis defines how to count days between dates and what is assumed as the length of a “year”. The implementation must carefully replicate Excel’s behavior for each basis, including all special rules and edge cases, to ensure the Rust/Polars function’s output matches Excel’s output exactly.

Basis 0 – US (NASD) 30/360

Definition: Basis 0 corresponds to the U.S. NASD 30/360 day-count convention ￼. This convention assumes each month has 30 days and each year has 360 days. The YEARFRAC result is calculated as if both dates were adjusted to a 30-day month, then counting days on a 360-day year ￼. The general formula can be expressed as:

\text{YEARFRAC}_{30/360\text{US}} = \frac{(D_2’ + 30 \times M_2’ + 360 \times Y_2’) - (D_1’ + 30 \times M_1’ + 360 \times Y_1’)}{360},

where the primed values D’, M’ are the adjusted day and month values after applying the US 30/360 rules. Essentially, the dates are converted to a serial day count on a 360-day calendar and then the difference is divided by 360.

Excel’s Adjustment Rules: Excel applies specific adjustments to the input dates’ day values before computing the difference ￼:
	•	End-of-February rule: If a date falls on the last day of February (Feb 28 in a common year or Feb 29 in a leap year), Excel adjusts that date’s day to 30 ￼. In other words, any date that is February 28 or 29 is treated as February 30 for this calculation. This applies to the start date, the end date, or both, as needed. (This rule effectively standardizes February end-of-month to behave like the 30th day.)
	•	Start date end-of-month: If the start_date is the last day of any month (including the adjusted Feb as above, or any 31st), then set its day to 30 ￼. This means if start_date is March 31, for example, it becomes March 30 for calculation purposes. If start_date was Feb 28/29 (the last day of Feb), by the previous rule it’s already treated as Feb 30 ￼, so this condition would then also make it 30 (which it already is).
	•	End date end-of-month: If the end_date is the last day of a month, Excel’s behavior depends on the start date’s day ￼:
	•	If start_date’s adjusted day is < 30, then Excel treats the end_date as if it were the 1st of the next month (effectively carrying it over). (In practice, leaving end_date at 31 in the same month when start < 30 yields the same day count result as moving it to the 1st of the next month ￼, so this is a conceptual way Excel handles it.)
	•	If start_date’s adjusted day is 30 or 31, then any end_date falling on the 31st is set to day 30 of that same month ￼.
	•	31-day adjustment: After the above, if one date still has a day value of 31 while the other has 30 (or 31), the 31 is changed to 30 ￼. (The rule can be stated: if D2 is 31 and D1 is 30 or 31, then set D2 = 30 ￼. Likewise, if D1 is 31, set D1 = 30 ￼. Excel’s procedure already covered the D1=31 case by setting it to 30 earlier, so the main remaining case is an end_date of 31 when start_date was also end-of-month.)

These rules ensure that date calculations align with a 30/360 calendar. In simpler terms, Excel’s US 30/360:
	•	Forces Feb 28 or 29 to be treated as the 30th (special-case for February end-of-month) ￼.
	•	Forces any 31st to be treated as 30th, with a particular handling for end dates when the start isn’t also near end-of-month ￼.

Edge Case – Feb 28/29 Quirk: A known quirk is that Excel’s YEARFRAC with basis 0 may give unexpected results when the start_date is the last day of February ￼. For example, certain date combinations can result in an off-by-one-day issue due to these adjustments. Microsoft’s documentation acknowledges that “The YEARFRAC function may return an incorrect result when using the US (NASD) 30/360 basis, and the start_date is the last day in February.” ￼. This is rooted in the rule interactions. For instance, if you calculate YEARFRAC on (Feb 29, 2016) to (Mar 1, 2016) under basis 0, Excel counts it as 1 day, but reversing the dates might yield –2 days for the day count before division (an asymmetry) ￼. This arises because when the start is Feb 29 (treated as Feb 30) and end is Mar 1, one day is counted, but if start is Mar 1 and end is Feb 29, the adjustment logic can end up counting two days difference in the opposite direction due to how the end-of-Feb adjustment is applied. In implementation, you must replicate Excel’s exact logic – including these quirks – so the results match Excel even in such edge cases. (It’s advisable to include unit tests for scenarios where start or end fall on Feb 28/29 to ensure consistency with Excel.)

Basis 1 – Actual/Actual

Definition: Basis 1 uses the Actual/Actual day count convention ￼. This means the actual number of days between the two dates is used as the numerator, and the denominator is the actual number of days in the corresponding year(s). Excel’s implementation of Actual/Actual is a bit unique because it must handle partial year spans and spans across multiple years.

Day count calculation: The numerator is simply the actual count of days between start_date and end_date (using the actual calendar difference). For example, Jan 1 to Jul 1 would count the exact number of days in that range.

Year length (denominator) logic: Excel determines the year length based on whether the period spans a leap day or crosses year boundaries:
	•	If the period between the dates falls within a single calendar year, Excel uses that year’s length. Specifically, if that year contains February 29 (leap year), the year length is 366, otherwise 365 ￼. For example, YEARFRAC(2021-01-01, 2021-08-01, basis 1) would divide the actual day count by 365 (since 2021 is not a leap year). If both dates are in 2020, a leap year, it would divide by 366.
	•	If the dates are in different years but the total span is less than or equal to 1 year (e.g., from mid-year of one year to mid-year of the next year), Excel checks if Feb 29 lies between the dates. If a Feb 29 is included in the range, it uses 366; otherwise 365 ￼ ￼. In other words, for a span that goes into the next year but doesn’t cover more than a year, the presence of a leap day in that interval causes a 366-day denominator. (Excel’s rule of thumb: “If the date range includes the date 29 February, the year is 366 days; otherwise it is 365 days.” ￼.)
	•	If the period spans more than one full year (i.e. more than 1 year apart, covering parts of at least two calendar years), Excel uses an average year length across the span ￼. In practice, Excel computes the fraction in this case by averaging the days in the years spanned. Technically, Excel calculates the total number of days between the dates and divides by the average number of days per year over that period ￼ ￼. This average is determined by summing the days in each calendar year covered and dividing by the number of years. For example, consider a span from 2019-07-01 to 2021-07-01: this crosses 2019, 2020, and 2021. Excel will take the total days between the dates and divide by the average days per year over 2019–2021. Since 2020 is leap (366 days) and 2019 and 2021 are common (365 each), the average year length = (365+366+365) / 3 = 365.333… days. The year fraction = total_days_diff / 365.333… in that case. In general, “if the argument basis is Actual/actual, the year length used is the average length of the years that the range crosses” ￼. This ensures the fraction accurately reflects multiple year spans.

Leap year considerations: The above logic inherently handles leap years:
	•	Within one year, a leap year yields a denominator of 366 ￼.
	•	Across years, any leap year in the span will increase the average year length accordingly ￼. If the span includes portions of leap and non-leap years, the averaging accounts for it.

Example: For a concrete example, the period from 2018-02-28 to 2020-05-17 (as in the crate’s README example) on Actual/Actual basis would be calculated by Excel in a multi-year manner. The total days are counted exactly, and since 2018–2020 spans 3 years, Excel finds the average days/year for 2018, 2019, 2020 and divides by that. The result should match Excel’s output (which in the example was ~42.21424933147 years for that long span).

Summary for implementation: When implementing basis 1 in Rust:
	•	Calculate the exact day difference (likely as an i64 of days between the two pl.Date values).
	•	If start and end are in the same year, use 365 or 366 accordingly ￼.
	•	If in different years, determine if the interval < 1 year: one way is to check if end_date is less than one year after start_date by date (Excel’s internal logic was complex; a safe approach is to directly check if end_date - start_date < 365 days or similar, but be careful around leap year boundaries). If the range is short and crosses Feb 29, use 366, otherwise 365 ￼.
	•	If the span >= 1 year, compute the average days per year: iterate through each year from start_year to end_year, sum the days in each year, divide by number of years, and use that as the denominator ￼ ￼. (This reproduces Excel’s approach for long spans.)
	•	Then return days_diff / year_length as a floating-point fraction (f64). Ensure double precision is used to match Excel (which uses IEEE 754 double for calculations).

Basis 2 – Actual/360

Definition: Basis 2 is the Actual/360 convention ￼. It uses the actual number of days between the dates as the numerator (like basis 1) but assumes a 360-day year for the denominator, regardless of calendar year lengths.

The formula for YEARFRAC under Actual/360 is straightforward:
\text{YEARFRAC}_{\text{Actual/360}} = \frac{\text{ActualDaysBetween}(start, end)}{360}.

There are no complex date adjustments or leap year checks for the denominator:
	•	The numerator = actual days count (each day is counted truly, including Feb 29 if it lies between the dates).
	•	The denominator = 360 (constant). Excel’s documentation confirms this is simply “similar to Basis 1, but only has 360 days per year.” ￼

Implications: This means every day counts as 1/360 of a year. For example, a 360-day span yields exactly 1.0, a 180-day span yields 0.5, and a full calendar year (365 days) would yield ~1.0139 (since it assumes the year is a bit longer than 360). Leap years are not given any special weight beyond contributing to the actual day count in the numerator (so a 366-day span would yield 1.0167).

Edge cases: There are essentially no special edge cases in Actual/360 aside from ensuring valid dates:
	•	No end-of-month adjustments (dates are used as-is for counting days).
	•	No leap year adjustments to the base; leap days simply make the fraction > 1 if the period is a full calendar year.
	•	If start_date equals end_date, YEARFRAC returns 0. If start_date is after end_date, Excel will return a positive fraction as noted (since it takes absolute difference) – but if implementing sign-sensitive logic, the raw calculation could yield a negative before taking absolute. In replication, you may simply take the absolute day count difference.

Implementing this in Rust is simple: use the day difference and divide by 360.0. Just be sure to use floating-point division to match Excel’s floating behavior.

Basis 3 – Actual/365

Definition: Basis 3 is Actual/365 (sometimes called “Actual/365 Fixed”) ￼. It is analogous to Actual/360, but uses a 365-day year as the fixed denominator. Excel treats this as “always 365 days per year” regardless of leap years ￼.

The formula:
\text{YEARFRAC}_{\text{Actual/365}} = \frac{\text{ActualDaysBetween}(start, end)}{365}.

Behavior: Every day is counted, and each day represents 1/365 of a year. A 365-day interval yields 1.0 exactly; a 366-day interval yields ~1.00274 (slightly over a year), because the convention does not account for the 366th day as making the year longer. This basis is commonly used in certain financial contexts (e.g., UK government bonds use Act/365 Fixed).

Leap year handling: There is no special-case handling of leap years in the formula – the presence of Feb 29 only affects the numerator (day count), not the denominator. The denominator remains 365 for all calculations ￼. So if your period includes a leap day, the fraction will be a bit larger than 1 for a full year span. If implementing, just be mindful that this is expected and correct for this basis.

Edge cases: Similar to Actual/360, there are no date adjustments needed. Use the absolute day difference and divide by 365. A possible edge consideration: If the date range happens to exactly span a leap year (e.g., 2020-01-01 to 2021-01-01, which is 366 days), Excel’s YEARFRAC(basis 3) would return 366/365 = 1.00274…, whereas basis 1 (Actual/Actual) would return 1.0 for the same range because it recognizes the year length was 366. This is an intentional difference in conventions. The implementation should simply follow the rule of 365-day year.

Basis 4 – European 30/360

Definition: Basis 4 corresponds to the European 30/360 convention ￼. Like the US 30/360, it assumes 30-day months and 360-day years for the calculation, but it handles end-of-month dates slightly differently (more strictly). The European method is sometimes called 30E/360 or 30/360 ICMA.

The formula structure is the same form as for basis 0:
\text{YEARFRAC}_{30/360\text{EU}} = \frac{(D_2’’ + 30 M_2’’ + 360 Y_2) - (D_1’’ + 30 M_1’’ + 360 Y_1)}{360},
with D_1’’, D_2’’ being adjusted day values per European rules.

Excel’s European 30/360 Rules: The European convention’s adjustments are simpler than the US method ￼ ￼:
	•	If a date falls on the 31st of any month, that date’s day value is reduced to 30 ￼. This applies to both start and end dates independently. (For example, if start_date is March 31, it is treated as March 30. If end_date is July 31, it becomes July 30.)
	•	No special February rule: Unlike the US basis, the European basis does not have a special case for February 28 or 29. Dates in February are not forced to 30. For instance, Feb 28 remains 28, and Feb 29 remains 29 under basis 4 (unless of course the date is Feb 29 and one applies the “if 31 then 30” rule – but February never has a 31st, so this doesn’t apply). In Excel, this means that end-of-February is handled just like any other day; only literal 31st dates are adjusted ￼. (The Office Open XML spec text had an error suggesting otherwise ￼, but the actual Excel implementation follows the standard European definition. Exceljet confirms that under the European convention, only dates that are the 31st are changed to 30 ￼.)
	•	There is no conditional interplay between start and end date as in the US method. Each date is adjusted purely based on its own value (31 or not).

After adjusting any 31s to 30, the day count is calculated similarly: days = (D_2’’ + 30 M_2 + 360 Y_2) - (D_1’’ + 30 M_1 + 360 Y_1), then divided by 360.

Differences vs US 30/360: In summary, basis 4 treats month-end consistently: 31 → 30 for both dates, and doesn’t treat Feb 28/29 specially. By contrast, basis 0 has nuanced rules (adjust Feb and handle the second date’s 31 based on the first date). Practically, this means basis 4 and basis 0 can yield different results for certain end-of-month date pairs. For example, consider start = Jan 31 and end = Feb 28 (non-leap year):
	•	US 30/360 (basis 0): Start31→30, EndFeb28→30 (special rule), difference will count an entire 30-day month difference (result ~0.08333).
	•	European 30/360 (basis 4): Start31→30, EndFeb28 stays 28, difference counted is 28 vs 30 (result ~0.07778).

Excel’s YEARFRAC will reflect those differences when basis is 0 vs 4. The Rust implementation should enforce the European rules for basis 4 exactly: adjust only 31s, no Feb tweaks ￼.

Edge cases: Because European 30/360 doesn’t do the conditional logic, it is straightforward to implement:
	•	Change any date that falls on the 31st to day 30.
	•	Then compute the 360-day calendar difference and divide by 360.
The result will always be the same sign (Excel will take absolute as usual). Reversed date order yields the same fraction magnitude (the European method is symmetric in the sense that if you swap dates, aside from the sign, the day count difference will be consistent – unlike the slight asymmetry noted in the US method’s quirk).

Excel’s Handling of Special Cases and Implementation Notes

Leap Years and Date Values

Each basis handles leap years differently, as described above:
	•	Basis 0 and 4 (30/360): Leap days might be implicitly handled by the Feb 28/29 rule (in US) or not at all (in EU). These conventions pretend all years have 360 days, so they do not treat a leap day as extending the year length – it’s just part of the day count adjustment rules.
	•	Basis 1 (Actual/Actual): Leap years explicitly affect the calculation. If a leap day is in the range, it can make the denominator 366 or increase the average year length ￼ ￼. The numerator (actual days) of course counts Feb 29 as a day.
	•	Basis 2 (Actual/360): Leap days are counted in the numerator but the year is always 360 days, so a leap year interval yields >1.0 fraction.
	•	Basis 3 (Actual/365): Leap days counted in numerator, denominator fixed at 365.

Excel’s 1900 Date System Quirk: It’s worth noting that Excel’s date serial system (by default) treats 1900 as a leap year even though it wasn’t (this is the famous “1900 bug” for compatibility). This means Excel’s serial date 60 represents 29-Feb-1900, which is not a real date. For YEARFRAC, this typically isn’t an issue unless dates around that period are used, in which case Excel’s day count might be off by one day around Feb 1900. In a Rust implementation using Polars (which likely uses proleptic Gregorian calendar without this bug), you do not need to emulate the 1900 bug – you can rely on correct date arithmetic. However, be aware that if you were matching Excel for dates in early 1900, there could be a one-day discrepancy due to Excel’s bug. Usually, this can be ignored unless strict Excel parity for 1900 is required.

Invalid Inputs and Excel Errors

Excel’s YEARFRAC will return an error in certain cases:
	•	If start_date or end_date is not a valid date value, YEARFRAC returns a #VALUE! error ￼. In a Polars context, this means if the pl.Date inputs are null or non-date, the function should produce an error or None.
	•	If basis is outside the range 0–4, Excel returns a #NUM! error ￼. The implementation should check the basis integer and handle out-of-range by raising an error or panic accordingly. (Similarly, if basis is a non-integer in Excel, it’s truncated to integer; in our implementation, basis will presumably be an integer enum or value.)
	•	If the dates are valid but out of Excel’s supported range (Excel’s serial dates typically run from 1900-01-01 to 9999-12-31 for the 1900 date system), Excel gives a #NUM! error ￼. Polars can handle a wider date range, but if we want to mimic Excel, we might restrict to Excel’s range. This is likely not necessary unless you specifically want to error on Excel-incompatible dates. For completeness, you might document that behavior: e.g., Excel would error on dates before 1900 in the default mode ￼.

In implementing YEARFRAC in Rust, you should ensure these error conditions are considered. For instance, you might implement the function to return a Result<f64, YearfracError> where you map invalid inputs to errors. At minimum, clamp or validate the basis and handle null dates.

Date Order and Sign of Result

As mentioned, Excel’s YEARFRAC ignores the sign of the date difference – it effectively uses ABS(end_date - start_date) in days ￼. In Excel, YEARFRAC(“2020-01-01”, “2019-01-01”) yields the same positive 1.0 as if the dates were reversed, rather than –1.0. If faithfully replicating Excel, your implementation should do the same (always return a non-negative fraction). The GitHub repo example code introduced a separate yearfrac_signed for cases where the user might want a signed result; but Excel’s native behavior is unsigned.

Therefore, in the core implementation, you should take the absolute day count difference between the two dates before applying the basis formula. If a negative result is desired, it can be handled by the caller (e.g., multiply by signum of the difference or use a separate flag/ function).

Floating-Point Precision and Matching Excel

Excel’s calculations are done in 64-bit binary floating point (IEEE 754 double precision). Your Rust implementation should use f64 for the fractional result to mirror this. That typically provides ~15 decimal digits of precision, which is the same as Excel’s precision for numbers.

Rounding/Truncation: Excel will not usually need any special rounding of the result – it will produce a binary floating value and format it for display. To match Excel output exactly, it’s usually enough to compute using f64 and not round prematurely. However, keep in mind that certain fractions (like 1/360 or 1/365) don’t have an exact binary representation, so you might see very tiny differences at the 15th decimal place if you’re not careful. For example, Excel might display 0.083333333333 for a 30/360 fraction of one month, whereas a direct f64 computation could be 0.08333333333333334 internally. These differences are on the order of 1e-17 and generally irrelevant, but for testing you may want to assert that the difference is within, say, 1e-12 or 1e-15 of Excel’s result.

Notably, some observers have pointed out minor precision quirks. For instance, the reciprocal of a one-day fraction in Excel sometimes gives a value like 360.000000000001 for basis 0 or 3 ￼. This is just a floating-point artifact. The key is to follow the same formula Excel does so that any tiny rounding error is consistent with Excel’s. Using Rust’s f64 should naturally do this as long as you don’t introduce extra rounding. Do not round the result to a fixed number of decimal places – just return the f64. This will preserve the tiny floating error if any, matching Excel’s binary result.

If exact matching to Excel’s displayed value is needed, you would need to mimic Excel’s formatting or rounding, but typically a numerical match (within 1e-9 or so) is sufficient for functional parity ￼ ￼.

Known Quirks and Inconsistencies

Aside from the basis-specific oddities already discussed (like the Feb 28/29 issue in US 30/360), here are a few additional notes:
	•	DAYS360 vs YEARFRAC: Excel also provides a DAYS360 function which returns the number of days difference on a 30/360 calendar. YEARFRAC with basis 0 or 4 essentially uses DAYS360 under the hood divided by 360. In Excel 2010+, DAYS360 has a method parameter (US or European). When implementing, it can be helpful to think of basis 0 and 4 as “compute days360 according to US or EU rules, then divide by 360.0”. Ensuring consistency with how Excel’s DAYS360 would count days is a good test of correctness.
	•	Asymmetry in US 30/360: As discussed, the US method can yield results where YEARFRAC(start, end, 0) + YEARFRAC(end, start, 0) is not exactly 0 (because one direction might round a day differently) ￼. This is a quirk of the convention, not a bug in the code per se. Your implementation should replicate that behavior. For instance, if your function returns 0.00278 for one order, it might return –0.00278 or –0.00279 for the reverse order, matching Excel. This is acceptable because Excel does the same. The key is to implement the rules in the exact sequence Excel does. The rules given above for basis 0 capture that sequence ￼.
	•	Testing against Excel: It’s highly recommended to cross-verify a range of test cases against Excel’s YEARFRAC for all bases. Include edge cases like:
	•	start and end on the same date (expect 0).
	•	start and end on consecutive days (should be ~0.00274 for basis3, ~0.00278 for basis2, etc.).
	•	dates around end of month boundaries (Jan 30 to Feb 28, Jan 31 to Feb 28, etc. for both basis 0 and 4 to see the difference).
	•	spans that include Feb 29 (e.g., Feb 28 to Mar 1 on various bases, a full leap year span on basis1 vs basis3).
	•	multi-year spans (to test the Actual/Actual averaging logic).
	•	invalid inputs (ensure errors are thrown similarly).

These tests will ensure your implementation in Rust/Polars mirrors Excel. The GitHub reference implementation confirms these behaviors and was tested to match Excel ￼ ￼, so you can use it as a benchmark (but write your code from scratch as intended).

Integration with Polars

Polars pl.Date type likely represents dates as an integer (perhaps days since epoch). To implement YEARFRAC, you’ll:
	1.	Convert the pl.Date values to a Rust NaiveDate or similar for easy calendar calculations (if Polars doesn’t have built-ins for day counts). The examples in the yearfrac crate used chrono::NaiveDate for date math ￼.
	2.	Compute the day count difference (consider using chrono’s signed_duration or converting to ordinal).
	3.	Apply the basis-specific rules as described.
	4.	Compute the fraction as f64.

Be mindful of Polars data structures – if this is to be vectorized over a series, you’ll want to apply the logic element-wise (perhaps via an apply on a column, or implementing it in Rust as a UDF). The logic is detailed enough that implementing it in Rust (for performance and clarity) is preferable to trying to express it in a pure Polars expression.

In summary, this specification lays out how Excel’s YEARFRAC works for each basis. Following these formulas and rules will allow you to replicate Excel’s output exactly in a Rust environment. By handling each basis’s formula, leap year rules, end-of-month adjustments, and error conditions, your implementation will align with Excel’s behavior down to its quirks. Test thoroughly, and you will have a robust yearfrac function for Polars that matches Excel’s logic and results.

Sources:
	•	Microsoft Office documentation on YEARFRAC basis conventions ￼ ￼ ￼
	•	Exceljet tutorial on YEARFRAC (overview of basis and date handling) ￼ ￼
	•	Office OpenXML and ODF specifications clarifying Actual/Actual and 30/360 rules ￼ ￼
	•	Rob Weir’s analysis of YEARFRAC inconsistencies (for understanding edge-case quirks) ￼ ￼.