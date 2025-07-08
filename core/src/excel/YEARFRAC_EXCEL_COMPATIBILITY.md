# YEARFRAC Excel Compatibility Documentation

This document describes the compatibility of our YEARFRAC implementation with Microsoft Excel, including known differences and quirks.

## Overview

Our YEARFRAC implementation aims to replicate Excel's behavior exactly, including its quirks and non-standard calculations. The function has been tested against known Excel outputs and implements all five basis options (0-4).

## Basis Options

### Basis 0: US (NASD) 30/360
- Assumes 30-day months and 360-day years
- Special handling for February end-of-month dates
- Jan 1 to Dec 31 returns exactly 1.0 (360 days)
- Complex rules for 31st day adjustments based on start date

### Basis 1: Actual/Actual
- Uses actual calendar days
- Denominator varies based on date span:
  - Same year: 365 or 366 (leap year)
  - Cross-year < 1 year: 366 if includes Feb 29, else 365
  - Multi-year: average days per year
- **Known Issue**: Not additive (see below)

### Basis 2: Actual/360
- Actual days divided by 360
- Simple calculation with no adjustments
- Full calendar year returns > 1.0

### Basis 3: Actual/365
- Actual days divided by 365
- Fixed denominator regardless of leap years
- Leap year returns > 1.0

### Basis 4: European 30/360
- Similar to US 30/360 but simpler rules
- Any 31st becomes 30th
- No special February handling
- Jan 1 to Dec 31 returns 359/360

## Known Excel Quirks Replicated

### 1. Non-Additivity of Basis 1
Excel's YEARFRAC with basis 1 is not additive. For example:
```
YEARFRAC(2011-12-30, 2012-01-04, 1) ≠ 
YEARFRAC(2011-12-30, 2012-01-01, 1) + YEARFRAC(2012-01-01, 2012-01-04, 1)
```
Our implementation replicates this behavior.

### 2. February 29 Asymmetry (Basis 0)
The US 30/360 method can produce asymmetric results when dealing with February 29:
- Feb 29, 2016 to Mar 1, 2016 = 1 day
- Mar 1, 2016 to Feb 29, 2016 = 1 day (when reversed)

### 3. Different Results for US vs European 30/360
For Jan 1 to Dec 31:
- US 30/360 (basis 0): Returns 1.0 (360 days)
- European 30/360 (basis 4): Returns 359/360

## Verification Against Excel

Our implementation has been verified with:
1. Known Excel outputs for standard date ranges
2. Edge cases involving leap years and month boundaries
3. Financial calculation examples
4. Problematic cases documented in financial libraries

## Differences from Financial Standards

Excel's YEARFRAC implementation differs from some financial standards:
- The Actual/Actual (basis 1) implementation differs from ISDA conventions
- Results may vary from LibreOffice and OpenOffice implementations
- The implementation has been benchmarked against the finmath library

## Testing

Comprehensive tests are included in `yearfrac_excel_verification.rs` that verify:
- Known Excel outputs
- Edge cases and quirks
- Financial calculation scenarios
- Consistency across all basis options

## Usage Recommendations

1. For financial calculations requiring Excel compatibility, use our implementation as-is
2. For new applications not requiring Excel compatibility, consider using standard day count conventions
3. Be aware of the non-additivity issue when using basis 1
4. Test thoroughly when migrating from or to Excel

## References

- Microsoft Excel YEARFRAC documentation
- Christian Fries' analysis of Excel YEARFRAC implementation
- finmath library day count convention implementations
- Various bug reports and discussions about Excel's implementation quirks