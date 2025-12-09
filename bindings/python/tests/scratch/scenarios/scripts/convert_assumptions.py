"""
Convert IntegratedLife assumption files from Excel to Parquet format.

This script reads the lifelib IntegratedLife model's Excel assumption files
and converts them to Parquet format for use with Gaspatchio.
"""
import pandas as pd
import polars as pl
from pathlib import Path
import numpy as np

# Paths
REF_DIR = Path(__file__).parent.parent / "ref" / "appliedlife"
INPUT_TABLES = REF_DIR / "input_tables"
ECONOMIC_DATA = REF_DIR / "economic_data"
MODEL_POINT_DATA = REF_DIR / "model_point_data"
MODEL_PARAMS_FILE = REF_DIR / "model_parameters.xlsx"

OUTPUT_DIR = Path(__file__).parent.parent / "assumptions"
OUTPUT_DIR.mkdir(exist_ok=True)


def convert_mortality_tables():
    """Convert mortality tables (select + ultimate) to parquet."""
    print("\n1. Converting mortality tables...")

    mort_file = INPUT_TABLES / "mortality_tables.xlsx"

    # Read table definitions
    table_defs = pd.read_excel(mort_file, sheet_name="TableDefs", index_col=0)
    print(f"   Found {len(table_defs)} mortality table definitions")

    # Filter to active tables
    active_tables = table_defs[table_defs['is_used'] == True]
    print(f"   Active tables: {list(active_tables.index)}")

    # Save table definitions
    table_defs_pl = pl.from_pandas(table_defs.reset_index())
    table_defs_pl.write_parquet(OUTPUT_DIR / "mortality_table_defs.parquet")
    print(f"   Saved mortality_table_defs.parquet")

    # Read ultimate mortality rates
    ultimate = pd.read_excel(mort_file, sheet_name="Ultimate", index_col=0)
    print(f"   Ultimate table shape: {ultimate.shape}")
    print(f"   Ultimate index name: {ultimate.index.name}")

    # Melt to long format: (attained_age, table_id) -> mort_rate
    ultimate_reset = ultimate.reset_index()
    # Get the index column name (might be 'Attained Age' or the index name)
    # Rename the index column to 'attained_age' first
    ultimate_reset.index.name = 'attained_age'
    if ultimate_reset.columns[0] == 'index':
        ultimate_reset = ultimate_reset.rename(columns={'index': 'attained_age_temp'})
    index_col = ultimate_reset.columns[0]
    print(f"   Index column name: {index_col}")

    ultimate_long = ultimate_reset.melt(
        id_vars=[index_col],
        var_name='table_id',
        value_name='mort_rate'
    )
    ultimate_long = ultimate_long.rename(columns={index_col: 'attained_age'})

    ultimate_pl = pl.from_pandas(ultimate_long)
    ultimate_pl.write_parquet(OUTPUT_DIR / "mortality_ultimate.parquet")
    print(f"   Saved mortality_ultimate.parquet ({len(ultimate_pl)} rows)")

    # Read select mortality rates for each active table
    select_rows = []
    for table_id in active_tables.index:
        if active_tables.loc[table_id, 'has_select']:
            try:
                select_df = pd.read_excel(mort_file, sheet_name=table_id, index_col=0)
                # Melt: (attained_age, duration) -> mort_rate
                # Note: Excel row index is entry_age, not attained_age
                # attained_age = entry_age + duration
                for col in select_df.columns:
                    # Excel columns are 1-indexed ('1', '2', ..., '25')
                    # Lifelib converts to 0-indexed (0, 1, ..., 24)
                    excel_col = int(col) if str(col).isdigit() else int(col)
                    duration = excel_col - 1  # Convert to 0-indexed like lifelib
                    for entry_age in select_df.index:
                        rate = select_df.loc[entry_age, col]
                        if pd.notna(rate):
                            select_rows.append({
                                'table_id': table_id,
                                'attained_age': int(entry_age) + duration,  # lifelib: att_age = entry_age + duration (0-indexed)
                                'duration': duration,
                                'mort_rate': float(rate)
                            })
                print(f"   Read select table {table_id}: {select_df.shape}")
            except Exception as e:
                print(f"   Warning: Could not read select table {table_id}: {e}")

    if select_rows:
        select_pl = pl.DataFrame(select_rows)
        select_pl.write_parquet(OUTPUT_DIR / "mortality_select.parquet")
        print(f"   Saved mortality_select.parquet ({len(select_pl)} rows)")

    return True


def convert_assumptions():
    """Convert assumption tables (lapse, mortality scalar, dynamic lapse)."""
    print("\n2. Converting assumption tables...")

    # Use 202312 version
    asmp_file = INPUT_TABLES / "assumptions_202312.xlsx"

    # Lapse rates
    lapse = pd.read_excel(asmp_file, sheet_name="Lapse", index_col=0)
    lapse_reset = lapse.reset_index()
    index_col = lapse_reset.columns[0]
    lapse_long = lapse_reset.melt(
        id_vars=[index_col],
        var_name='lapse_id',
        value_name='lapse_rate'
    )
    lapse_long = lapse_long.rename(columns={index_col: 'duration'})
    lapse_pl = pl.from_pandas(lapse_long)
    lapse_pl.write_parquet(OUTPUT_DIR / "lapse_rates.parquet")
    print(f"   Saved lapse_rates.parquet ({len(lapse_pl)} rows)")

    # Mortality scalars
    mort_scalar = pd.read_excel(asmp_file, sheet_name="Mortality", index_col=0)
    mort_scalar_reset = mort_scalar.reset_index()
    index_col = mort_scalar_reset.columns[0]
    mort_scalar_long = mort_scalar_reset.melt(
        id_vars=[index_col],
        var_name='scalar_id',
        value_name='mort_scalar'
    )
    mort_scalar_long = mort_scalar_long.rename(columns={index_col: 'duration'})
    mort_scalar_pl = pl.from_pandas(mort_scalar_long)
    mort_scalar_pl.write_parquet(OUTPUT_DIR / "mortality_scalars.parquet")
    print(f"   Saved mortality_scalars.parquet ({len(mort_scalar_pl)} rows)")

    # Dynamic lapse parameters
    dyn_lapse = pd.read_excel(asmp_file, sheet_name="DynLapse", index_col=0)
    dyn_lapse_pl = pl.from_pandas(dyn_lapse.reset_index())
    dyn_lapse_pl.write_parquet(OUTPUT_DIR / "dynamic_lapse_params.parquet")
    print(f"   Saved dynamic_lapse_params.parquet ({len(dyn_lapse_pl)} rows)")

    # Inflation rates
    try:
        inflation = pd.read_excel(asmp_file, sheet_name="Inflation", index_col=0)
        inflation_reset = inflation.reset_index()
        index_col = inflation_reset.columns[0]
        inflation_long = inflation_reset.melt(
            id_vars=[index_col],
            var_name='currency',
            value_name='inflation_rate'
        )
        inflation_long = inflation_long.rename(columns={index_col: 'duration'})
        inflation_pl = pl.from_pandas(inflation_long)
        inflation_pl.write_parquet(OUTPUT_DIR / "inflation_rates.parquet")
        print(f"   Saved inflation_rates.parquet ({len(inflation_pl)} rows)")
    except Exception as e:
        print(f"   Warning: Could not read Inflation sheet: {e}")

    return True


def convert_product_specs():
    """Convert product specification tables."""
    print("\n3. Converting product specification tables...")

    spec_file = INPUT_TABLES / "product_spec_tables.xlsx"

    # Surrender charges
    surr = pd.read_excel(spec_file, sheet_name="SurrCharge", index_col=0)
    surr_reset = surr.reset_index()
    index_col = surr_reset.columns[0]
    surr_long = surr_reset.melt(
        id_vars=[index_col],
        var_name='surr_charge_id',
        value_name='surr_charge_rate'
    )
    surr_long = surr_long.rename(columns={index_col: 'duration'})
    surr_pl = pl.from_pandas(surr_long)
    surr_pl.write_parquet(OUTPUT_DIR / "surrender_charges.parquet")
    print(f"   Saved surrender_charges.parquet ({len(surr_pl)} rows)")

    # Read product parameters from model_parameters.xlsx
    params_file = MODEL_PARAMS_FILE

    # GMXB product params
    try:
        gmxb_params = pd.read_excel(params_file, sheet_name="GMXB")
        gmxb_pl = pl.from_pandas(gmxb_params)
        gmxb_pl.write_parquet(OUTPUT_DIR / "product_params_gmxb.parquet")
        print(f"   Saved product_params_gmxb.parquet ({len(gmxb_pl)} rows)")
    except Exception as e:
        print(f"   Warning: Could not read GMXB sheet: {e}")

    # Space params
    try:
        space_params = pd.read_excel(params_file, sheet_name="SpaceParams")
        space_pl = pl.from_pandas(space_params)
        space_pl.write_parquet(OUTPUT_DIR / "space_params.parquet")
        print(f"   Saved space_params.parquet ({len(space_pl)} rows)")
    except Exception as e:
        print(f"   Warning: Could not read SpaceParams sheet: {e}")

    # Run params
    try:
        run_params = pd.read_excel(params_file, sheet_name="RunParams")
        run_pl = pl.from_pandas(run_params)
        run_pl.write_parquet(OUTPUT_DIR / "run_params.parquet")
        print(f"   Saved run_params.parquet ({len(run_pl)} rows)")
    except Exception as e:
        print(f"   Warning: Could not read RunParams sheet: {e}")

    return True


def convert_economic_data():
    """Convert economic data (risk-free rates, index parameters)."""
    print("\n4. Converting economic data...")

    # Index parameters - convert wide format to long format
    index_file = ECONOMIC_DATA / "index_parameters.xlsx"
    try:
        index_params = pd.read_excel(index_file, sheet_name="Params", index_col=0)
        # Transpose: rows become columns, columns become rows
        # Original: rows = [currency, return, volatility, risk_free, sharpe_ratio], columns = [FUND1-FUND6]
        # After transpose: rows = [FUND1-FUND6], columns = [currency, return, volatility, risk_free, sharpe_ratio]
        index_transposed = index_params.T
        index_transposed.index.name = 'fund_index'
        index_reset = index_transposed.reset_index()

        # Convert numeric columns properly
        for col in ['return', 'volatility', 'risk_free', 'sharpe_ratio']:
            if col in index_reset.columns:
                index_reset[col] = pd.to_numeric(index_reset[col], errors='coerce')

        index_pl = pl.from_pandas(index_reset)
        index_pl.write_parquet(OUTPUT_DIR / "index_parameters.parquet")
        print(f"   Saved index_parameters.parquet ({len(index_pl)} rows)")
        print(f"   Index params columns: {list(index_pl.columns)}")
    except Exception as e:
        print(f"   Warning: Could not read index parameters: {e}")
        import traceback
        traceback.print_exc()

    # Risk-free rates (202312)
    rf_file = ECONOMIC_DATA / "risk_free_202312.xlsx"
    try:
        # Read each scenario sheet
        scenarios = ['BASE', 'UP', 'DOWN']
        rf_rows = []

        for scen in scenarios:
            try:
                rf_df = pd.read_excel(rf_file, sheet_name=scen, index_col=0)
                for col in rf_df.columns:
                    for year in rf_df.index:
                        rate = rf_df.loc[year, col]
                        if pd.notna(rate):
                            rf_rows.append({
                                'scenario': scen,
                                'currency': col,
                                'year': int(year),
                                'forward_rate': float(rate)
                            })
                print(f"   Read risk-free scenario {scen}: {rf_df.shape}")
            except Exception as e:
                print(f"   Warning: Could not read {scen} sheet: {e}")

        if rf_rows:
            rf_pl = pl.DataFrame(rf_rows)
            rf_pl.write_parquet(OUTPUT_DIR / "risk_free_rates.parquet")
            print(f"   Saved risk_free_rates.parquet ({len(rf_pl)} rows)")
    except Exception as e:
        print(f"   Warning: Could not read risk-free rates: {e}")

    return True


def convert_model_points():
    """Convert model point CSVs to parquet."""
    print("\n5. Converting model points...")

    # Use the main GMXB file
    mp_file = MODEL_POINT_DATA / "model_point_2023Q4IF_GMXB.csv"

    if mp_file.exists():
        mp_df = pl.read_csv(mp_file)
        output_path = OUTPUT_DIR.parent / "model_points.parquet"
        mp_df.write_parquet(output_path)
        print(f"   Saved model_points.parquet ({len(mp_df)} rows)")
    else:
        print(f"   Warning: Model point file not found: {mp_file}")

    return True


def main():
    """Run all conversions."""
    print("=" * 60)
    print("Converting IntegratedLife assumptions to Parquet format")
    print("=" * 60)
    print(f"\nInput directory: {REF_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")

    convert_mortality_tables()
    convert_assumptions()
    convert_product_specs()
    convert_economic_data()
    convert_model_points()

    print("\n" + "=" * 60)
    print("Conversion complete!")
    print("=" * 60)

    # List output files
    print("\nOutput files:")
    for f in sorted(OUTPUT_DIR.glob("*.parquet")):
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name}: {size_kb:.1f} KB")

    # Check for model_points.parquet in parent
    mp_path = OUTPUT_DIR.parent / "model_points.parquet"
    if mp_path.exists():
        size_kb = mp_path.stat().st_size / 1024
        print(f"  ../model_points.parquet: {size_kb:.1f} KB")


if __name__ == "__main__":
    main()
