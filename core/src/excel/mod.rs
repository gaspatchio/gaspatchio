// ABOUTME: Excel module exports and organization
// ABOUTME: Provides Excel-compatible financial and date functions

pub mod irr;
pub mod pv;
pub mod yearfrac;

pub use irr::{irr, irr_output_type, IrrKwargs};
pub use pv::{pv, pv_output_type, PvKwargs};
pub use yearfrac::{yearfrac, yearfrac_output_type, YearFracKwargs};

#[cfg(test)]
mod irr_tests;
#[cfg(test)]
mod pv_tests;
#[cfg(test)]
mod yearfrac_tests;
