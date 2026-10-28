# /// script
# dependencies = [
#     "marimo",
#     "polars==1.44.2",
#     "ssb-parquedit==0.1.2",
# ]
# requires-python = ">=3.14"
# ///

import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import polars as pl
    from ssb_parquedit import ParquEdit

    con = ParquEdit.local()
    refresh, set_refresh = mo.state(0)
    return con, mo, pl, refresh, set_refresh


@app.cell
def table_picker(con, mo, refresh):
    _ = refresh()
    tables = con.list_tables()
    table = mo.ui.dropdown(options=tables, value=tables[0] if tables else None, label="Velg ParquEdit-tabell")
    mo.vstack([mo.md("# ParquEdit-dashboard\nVelg tabell, rad, rediger verdier og lagre endringen."), table])
    return table, tables


@app.cell
def data_view(con, mo, refresh, table, tables):
    _ = refresh()
    mo.stop(not tables, mo.md("Fant ingen tabeller i ParquEdit.local()."))
    data = con.view(table_name=table.value, output_format="polars")
    rows = mo.ui.table(data=data, selection="single", pagination=True, page_size=15, label="Velg rad")
    rows
    return data, rows


@app.cell
def row_editor(data, mo, rows):
    selected = rows.value
    has_selection = selected is not None and selected.height > 0
    mo.stop(not has_selection, mo.md("Velg en rad i tabellen over for å redigere den."))
    row = selected.row(0, named=True)
    widgets = {c: mo.ui.text(value="" if row[c] is None else str(row[c]), label=f"{c} (nå: {row[c]})", full_width=True) for c in data.columns if c != "rowid"}
    widgets["reason"] = mo.ui.dropdown(options=["REVIEW", "OTHER_SOURCE", "OWNER", "DUPLICATE", "OTHER"], value="REVIEW", label="Årsak")
    widgets["comment"] = mo.ui.text_area(label="Kommentar", full_width=True)
    form = mo.md("### Rediger valgt rad\n" + "\n".join(f"**{c}** {{{c}}}" for c in data.columns if c != "rowid") + "\n\nÅrsak: {reason}\n\nKommentar: {comment}").batch(**widgets).form(submit_button_label="Lagre med ParquEdit")
    form

    return form, row


@app.cell
def save_changes(con, data, form, mo, refresh, row, set_refresh, table):
    if form.value is not None and row is not None:
        values = form.value
        changes = {c: values[c] for c in data.columns if c != "rowid" and str(values[c]) != str(row[c])}
        if changes:
            con.edit(table_name=table.value, rowid=row["rowid"], changes=changes, change_event_reason=values["reason"], change_comment=values["comment"])
            set_refresh(refresh() + 1)
            mo.status.toast("Endringen ble lagret med ParquEdit.")
    return


@app.cell(hide_code=True)
def endringshistorikk(con, mo, pl, refresh, table, tables):
    _ = refresh()
    edit_history = con.get_edits(table.value) if tables else None

    def _format_history_value(value):
        if value is None:
            return ""
        return str(value).replace("{'", "").replace("'}", "").replace("'", "")

    history_rows = [] if edit_history is None else [
        {
            "Tidspunkt": str(record["snapshot_time"])[:19],
            "Rad": record["rowid"],
            "Endring": record["change_type"],
            "Felt": ", ".join(record["new_values"].keys()) if isinstance(record["new_values"], dict) else "",
            "Fra": _format_history_value(record["old_values"]),
            "Til": _format_history_value(record["new_values"]),
            "Årsak": record["change_event_reason"] or "",
            "Utført av": record["changed_by"] or record["author"] or "",
            "Kommentar": record["change_comment"] or "",
        }
        for record in edit_history.sort_values("snapshot_time", ascending=False).to_dict("records")
    ]
    history_view = pl.DataFrame(history_rows)
    history_table = mo.ui.table(
        data=history_view,
        pagination=True,
        page_size=10,
        label="Endringshistorikk",
    )
    mo.vstack([
        mo.md("## Endringshistorikk\n\nNyeste endringer vises øverst."),
        history_table,
    ])

    return


if __name__ == "__main__":
    app.run()
