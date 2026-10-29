# /// script
# dependencies = [
#     "marimo",
#     "ssb-parquedit==0.1.2",
# ]
# requires-python = ">=3.14"
# ///

import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")


@app.cell
def imports():
    import marimo as mo
    from ssb_parquedit import ParquEdit

    pe = ParquEdit.local()
    return mo, pe


@app.cell(hide_code=True)
def title(mo):
    title = mo.md("# ParquEdit: rediger en rad")
    title
    return


@app.cell(hide_code=True)
def table_selector(mo, pe):
    tables = pe.list_tables()
    table_selector = mo.ui.dropdown(
        options=tables,
        value=tables[0] if tables else None,
        label="Velg tabell",
    )
    table_selector
    return (table_selector,)


@app.cell(hide_code=True)
def rows(mo, pe, table_selector):
    selected_table = table_selector.value
    rows = pe.view(selected_table, limit=100) if selected_table else []
    mo.md("")
    return rows, selected_table


@app.cell(hide_code=True)
def row_table(mo, rows):
    row_table = mo.ui.table(
        rows,
        selection="single",
        pagination=True,
        page_size=25,
        label="Marker raden du vil redigere",
    )
    row_table
    return (row_table,)


@app.cell(hide_code=True)
def selected_row(mo, row_table, set_saved):
    selected_rows = row_table.value
    if selected_rows is None or len(selected_rows) == 0:
        selected_row = None
    else:
        selected_row = selected_rows.iloc[0].to_dict()
        set_saved(False)
    mo.md("")
    return (selected_row,)


@app.cell(hide_code=True)
def save_state(mo):
    saved, set_saved = mo.state(False)
    mo.md("")
    return saved, set_saved


@app.cell(hide_code=True)
def edit_form(mo, saved, selected_row):
    editable_columns = [
        column for column in (selected_row or {}).keys()
        if column not in {"rowid", "_rowid"}
    ]
    row_fields = {
        column: mo.ui.text(
            value="" if selected_row[column] is None else str(selected_row[column]),
            label=column,
        )
        for column in editable_columns
    }
    change_reason = mo.ui.dropdown(
        options=["OTHER_SOURCE", "REVIEW", "OWNER", "MARGINAL_UNIT", "DUPLICATE", "OTHER"],
        label="Endringsårsak (påkrevd)",
    )
    comment = mo.ui.text_area(
        label="Kommentar (påkrevd)",
        placeholder="Beskriv hvorfor raden endres",
    )
    save_button = mo.ui.run_button(label="Lagre endring")
    form = mo.vstack([
        mo.md("### Endre valgt rad"),
        *row_fields.values(),
        change_reason,
        comment,
        save_button,
    ])
    if selected_row is None:
        display = mo.md("Velg en rad for å vise endringsskjemaet.")
    elif saved():
        display = mo.md("✅ Endringen er lagret. Velg en ny rad for å redigere.")
    else:
        display = form
    display
    return change_reason, comment, editable_columns, row_fields, save_button


@app.cell(hide_code=True)
def save_change(
    change_reason,
    comment,
    editable_columns,
    mo,
    pe,
    row_fields,
    save_button,
    selected_row,
    selected_table,
    set_saved,
):
    if save_button.value:
        if selected_row is None:
            message = mo.md("⚠️ Marker en rad før du lagrer.")
        elif not comment.value.strip():
            message = mo.md("⚠️ Skriv en kommentar før du lagrer.")
        else:
            changes = {}
            for column in editable_columns:
                raw_value = row_fields[column].value
                original_value = selected_row[column]
                if raw_value == "" and original_value is None:
                    new_value = None
                elif isinstance(original_value, bool):
                    new_value = raw_value.strip().lower() in {"true", "1", "ja"}
                elif isinstance(original_value, int) and not isinstance(original_value, bool):
                    new_value = int(raw_value)
                elif isinstance(original_value, float):
                    new_value = float(raw_value)
                else:
                    new_value = raw_value
                if new_value != original_value:
                    changes[column] = new_value

            if changes:
                rowid_key = "rowid" if "rowid" in selected_row else "_rowid"
                pe.edit(
                    selected_table,
                    int(selected_row[rowid_key]),
                    changes,
                    change_event_reason=change_reason.value,
                    change_comment=comment.value.strip(),
                )
                set_saved(True)
                message = mo.md("✅ Endringen er lagret.")
            else:
                message = mo.md("ℹ️ Ingen felt er endret.")
    else:
        message = mo.md("Velg en rad for å vise endringsskjemaet.")
    message
    return (message,)


@app.cell
def _(message, mo, pe, saved, selected_table):
    history_columns = [
        "snapshot_time",
        "change_type",
        "changed_by",
        "rowid",
        "user_defined_id",
        "change_event_reason",
        "change_comment",
        "old_values",
        "new_values",
    ]
    _ = saved(), message
    edits = pe.get_edits(selected_table) if selected_table else None
    if edits is None or edits.empty:
        history_content = mo.md("Ingen endringer er registrert for denne tabellen ennå.")
    else:
        available_columns = [col for col in history_columns if col in edits.columns]
        history_content = mo.ui.table(
            edits[available_columns],
            selection=None,
            pagination=True,
            page_size=10,
            label="Registrerte endringer",
        )
    history_section = mo.vstack([
        mo.md("### Endringshistorikk"),
        history_content,
    ])
    history_section
    return


if __name__ == "__main__":
    app.run()
