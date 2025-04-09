import marimo

__generated_with = "0.12.4"
app = marimo.App(width="medium")


@app.cell
def _():
    import polars as pl
    import datacompy
    from datacompy import PolarsCompare
    return PolarsCompare, datacompy, pl


@app.cell
def _(pl):
    policy_id = 1

    ss_df = pl.read_csv(f"jobs/example/reconcillation/{policy_id}_data.csv")
    model_df = pl.read_csv(f"jobs/example/reconcillation/{policy_id}_gs_output.csv")
    return model_df, policy_id, ss_df


@app.cell
def _(PolarsCompare, model_df, ss_df):
    compare = PolarsCompare(
        ss_df,
        model_df,
        join_columns='month',  #You can also specify a list of columns
        abs_tol=0.0001,
        rel_tol=0,
        df1_name='original',
        df2_name='new')
    return (compare,)


@app.cell
def _(compare):
    print(compare.report())
    return


if __name__ == "__main__":
    app.run()
