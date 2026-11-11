// The day page's editors: plans and reflections as text, where a line that
// is a task's ends with the task's anchor (" ^t91bd0a44") and the anchor is
// drawn as a chip.
//
// Each editor sits over a <textarea data-task-document="plan|reflection">,
// which stays the form field: the editor copies its text into it on every
// change, and the form posts it with the text the page was loaded with
// (<name>-base), so the server applies only what was changed here. Without
// this script the textarea shows the same text, anchors and all.
//
// A chip is one unit: the cursor steps over it, Backspace takes it out (the
// line is no longer that task's), and cutting a line carries it along. In a
// plan, clicking it does a step of the task or takes the last one back.

import { EditorState, Prec, RangeSetBuilder, StateEffect } from "@codemirror/state";
import {
    Decoration,
    EditorView,
    ViewPlugin,
    WidgetType,
    keymap,
    placeholder,
} from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";

import { detach } from "./autosize.js";
import { Notifier } from "./notifier";
import { localDate, makeId } from "./utils";

// As services/tasks/documents.py reads it: only a trailing anchor counts. The
// chip takes one space with it, so that a space typed before it stays text
// (the server drops whatever space is left before an anchor).
const ANCHOR = /[ \t]\^t([0-9a-f]{8})[ \t]*$/;

const form = document.getElementById("daily-form");
const chipsElement = document.getElementById("task-document-chips");

// What is known of each task on the page, by anchor: {id, text, display,
// done, total, done_count}. An anchor typed or pasted in from elsewhere is
// not in here until the page is saved.
const chips = chipsElement ? JSON.parse(chipsElement.textContent) : {};
const busy = new Set();
const views = [];

// Sent to every editor when a task changed: its chips are drawn anew.
const tasksChanged = StateEffect.define();

function anchorOf(line) {
    const found = ANCHOR.exec(line.text);
    if (!found) return null;
    return { from: line.from + found.index, to: line.to, anchor: found[1] };
}

class Chip extends WidgetType {
    constructor(anchor, kind) {
        super();
        this.anchor = anchor;
        this.kind = kind;
        const task = chips[anchor];
        this.state = task
            ? `${task.done}:${task.done_count}:${busy.has(anchor)}`
            : "unknown";
    }

    eq(other) {
        return (
            other.anchor === this.anchor &&
            other.kind === this.kind &&
            other.state === this.state
        );
    }

    toDOM() {
        const task = chips[this.anchor];
        const el = document.createElement("span");
        el.className = "task-chip";

        if (!task) {
            el.textContent = "◷";
            el.title = "A task; save the page to see it";
            return el;
        }

        el.classList.toggle("done", task.done);
        el.classList.toggle("busy", busy.has(this.anchor));
        if (task.total > 1) {
            el.textContent = `${Math.min(task.done_count, task.total)}/${task.total}`;
        } else {
            el.textContent = task.done ? "✓" : "○";
        }

        if (this.kind === "plan") {
            el.setAttribute("role", "button");
            el.title = task.done
                ? `Done: ${task.text}. Click to take it back`
                : `Task: ${task.text}. Click when it is done`;
            el.addEventListener("mousedown", (event) => {
                event.preventDefault();
                toggle(this.anchor);
            });
        } else {
            el.title = `About the task: ${task.text}`;
        }
        return el;
    }

    ignoreEvent() {
        return true;
    }
}

function decorate(view, kind) {
    const builder = new RangeSetBuilder();
    for (const { from, to } of view.visibleRanges) {
        for (let pos = from; pos <= to; ) {
            const line = view.state.doc.lineAt(pos);
            const found = anchorOf(line);
            if (found) {
                if (kind === "plan" && chips[found.anchor]?.done) {
                    builder.add(
                        line.from,
                        line.from,
                        Decoration.line({ class: "task-done" }),
                    );
                }
                builder.add(
                    found.from,
                    found.to,
                    Decoration.replace({ widget: new Chip(found.anchor, kind) }),
                );
            }
            pos = line.to + 1;
        }
    }
    return builder.finish();
}

function chipPlugin(kind) {
    return ViewPlugin.fromClass(
        class {
            constructor(view) {
                this.decorations = decorate(view, kind);
            }

            update(update) {
                const told = update.transactions.some((transaction) =>
                    transaction.effects.some((effect) => effect.is(tasksChanged)),
                );
                if (update.docChanged || update.viewportChanged || told) {
                    this.decorations = decorate(update.view, kind);
                }
            }
        },
        {
            decorations: (plugin) => plugin.decorations,
            provide: (plugin) =>
                EditorView.atomicRanges.of(
                    (view) => view.plugin(plugin)?.decorations || Decoration.none,
                ),
        },
    );
}

// --- Keeping an anchor at the end of its line ---
//
// An anchor only counts where a line ends. Three ordinary edits would leave
// one in the middle of a line: typing after the chip, Enter inside the line
// (the anchor would go to the new line with the tail), and joining two lines.

// Text typed where the line ends, after the chip, goes before the chip.
const typeBeforeChip = EditorState.transactionFilter.of((transaction) => {
    if (!transaction.docChanged || !transaction.isUserEvent("input")) {
        return transaction;
    }

    let moved = null;
    let changes = 0;
    transaction.changes.iterChanges((fromA, toA, _fromB, _toB, inserted) => {
        changes += 1;
        const text = inserted.toString();
        if (fromA !== toA || !text || text.includes("\n")) return;
        const line = transaction.startState.doc.lineAt(fromA);
        const found = anchorOf(line);
        if (found && fromA === line.to) {
            moved = { at: found.from, text };
        }
    });
    if (!moved || changes !== 1) return transaction;

    return {
        changes: { from: moved.at, insert: moved.text },
        selection: { anchor: moved.at + moved.text.length },
        userEvent: "input.type",
        scrollIntoView: true,
    };
});

// Enter inside a task's line: the task stays with the head of the line, the
// tail goes to a new line of its own.
function splitLine(view) {
    const { state } = view;
    const range = state.selection.main;
    if (!range.empty) return false;

    const line = state.doc.lineAt(range.head);
    const found = anchorOf(line);
    if (!found || range.head > found.from) return false;

    const chip = state.doc.sliceString(found.from, found.to);
    const tail = state.doc.sliceString(range.head, found.from);
    view.dispatch({
        changes: { from: range.head, to: line.to, insert: `${chip}\n${tail}` },
        selection: { anchor: range.head + chip.length + 1 },
        userEvent: "input",
        scrollIntoView: true,
    });
    return true;
}

// Backspace where a line starts, below a task's line: the text joins the
// task's line before its chip. Two tasks' lines don't join.
function joinWithLineAbove(view) {
    const { state } = view;
    const range = state.selection.main;
    if (!range.empty) return false;

    const line = state.doc.lineAt(range.head);
    if (range.head !== line.from || line.number === 1) return false;

    const above = anchorOf(state.doc.line(line.number - 1));
    if (!above) return false;
    if (anchorOf(line)) return true;

    const chip = state.doc.sliceString(above.from, above.to);
    view.dispatch({
        changes: { from: above.from, to: line.to, insert: `${line.text}${chip}` },
        selection: { anchor: above.from },
        userEvent: "delete.backward",
        scrollIntoView: true,
    });
    return true;
}

// Delete where a task's line ends: the same, with the line below.
function joinWithLineBelow(view) {
    const { state } = view;
    const range = state.selection.main;
    if (!range.empty) return false;

    const line = state.doc.lineAt(range.head);
    const found = anchorOf(line);
    if (!found || range.head !== line.to || line.number === state.doc.lines) {
        return false;
    }

    const below = state.doc.line(line.number + 1);
    if (anchorOf(below)) return true;

    const chip = state.doc.sliceString(found.from, found.to);
    view.dispatch({
        changes: { from: found.from, to: below.to, insert: `${below.text}${chip}` },
        selection: { anchor: found.from },
        userEvent: "delete.forward",
        scrollIntoView: true,
    });
    return true;
}

const anchorKeys = Prec.high(
    keymap.of([
        { key: "Enter", run: splitLine },
        { key: "Backspace", run: joinWithLineAbove },
        { key: "Delete", run: joinWithLineBelow },
    ]),
);

// --- Doing a task from its chip ---

function unsaved() {
    return views.some(
        ({ view, base }) => view.state.doc.toString() !== base.replace(/\r\n?/g, "\n"),
    );
}

function redraw() {
    views.forEach(({ view }) => view.dispatch({ effects: tasksChanged.of(null) }));
}

async function toggle(anchor) {
    const task = chips[anchor];
    if (!task || busy.has(anchor)) return;

    const notifier = Notifier({ time: 4000 });
    const token = form.querySelector("[name=csrfmiddlewaretoken]");
    // A task with steps left gets another step; a done one is taken back.
    const action = task.done ? "reopen" : "complete";
    const body = task.done
        ? {}
        : {
              day: form.dataset.completionDay || localDate(),
              idempotency_key: makeId(),
          };

    busy.add(anchor);
    redraw();
    try {
        const response = await fetch(`/api/v1/tasks/${task.id}/${action}/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": token ? token.value : "",
            },
            body: JSON.stringify(body),
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const now = await response.json();
        chips[anchor] = {
            ...task,
            done: now.done,
            done_count: now.done_count,
            display: now.display,
        };
    } catch (error) {
        notifier.error(`Could not save that: ${error.message}`);
        return;
    } finally {
        busy.delete(anchor);
        redraw();
    }

    if (!unsaved()) {
        // Nothing typed here would be lost: show the page as it is now, the
        // reflection's new line included.
        window.location.reload();
        return;
    }
    notifier.success(
        action === "complete"
            ? "Done. Its reflection line shows once you save the page."
            : "Taken back.",
    );
}

// --- Mounting ---

const theme = EditorView.theme({
    "&": {
        color: "#e27410",
        fontSize: "1.4rem",
        borderBottom: "1px solid #d8dbdb",
    },
    "&.cm-focused": { outline: "none" },
    ".cm-scroller": {
        fontFamily: "'Raleway', sans-serif",
        lineHeight: "1.3",
        overflow: "visible",
    },
    ".cm-content": {
        padding: "0 0 0.25rem",
        minHeight: "8rem",
        caretColor: "#e27410",
    },
    ".cm-line": { padding: "0" },
    ".cm-placeholder": { fontStyle: "italic", color: "#999" },
});

function mount(textarea) {
    const kind = textarea.dataset.taskDocument;
    const baseInput = form.querySelector(`[name="${textarea.name}-base"]`);

    const parent = document.createElement("div");
    parent.className = "task-document";
    textarea.insertAdjacentElement("afterend", parent);

    const view = new EditorView({
        parent,
        state: EditorState.create({
            doc: textarea.value,
            extensions: [
                history(),
                anchorKeys,
                keymap.of([...defaultKeymap, ...historyKeymap]),
                typeBeforeChip,
                chipPlugin(kind),
                placeholder(textarea.placeholder),
                EditorView.lineWrapping,
                EditorView.contentAttributes.of({
                    "aria-label": textarea.placeholder,
                }),
                EditorView.updateListener.of((update) => {
                    if (update.docChanged) {
                        textarea.value = update.state.doc.toString();
                    }
                }),
                theme,
            ],
        }),
    });

    // The textarea stays in the form, out of sight; the autosizer attached to
    // it before this chunk loaded has nothing left to size.
    detach(textarea);
    textarea.style.display = "none";

    views.push({ view, base: baseInput ? baseInput.value : textarea.value });
}

if (form) {
    form.querySelectorAll("textarea[data-task-document]").forEach(mount);
}
