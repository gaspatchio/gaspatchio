// ABOUTME: Excel module exports and organization
// ABOUTME: Provides Excel-compatible financial and date functions

pub mod yearfrac;

pub use yearfrac::{yearfrac, yearfrac_output_type, YearFracKwargs};

#[cfg(test)]
mod yearfrac_tests;