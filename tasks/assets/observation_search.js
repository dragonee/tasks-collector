// Client-side filter for the observation list (/observations/).
//
// All searchable text (situation, interpretation, approach and every update
// comment) is already rendered into each article's `data-search` attribute by
// the template, so this builds small in-memory stem indexes from the DOM and
// hides the articles that don't match the query.
//
// Stemming handles both Polish and English: every token is reduced by both the
// Polish (lunr-languages) and English (lunr core) stemmers. Polish is only
// lightly stemmed by the rule-based stemmer (it folds declensions such as
// "park"/"parku" but not whole verb families), so we additionally match on a
// shared stem prefix — this conflates families like "bieganie"/"biegania"/
// "biegał" that differ only past a common root. Words are AND-ed together.

import lunr from "lunr";
import stemmerSupport from "lunr-languages/lunr.stemmer.support";
import polish from "lunr-languages/lunr.pl";

stemmerSupport(lunr);
polish(lunr);

const plStemmer = lunr.pl.stemmer;
const enStemmer = lunr.stemmer;

// Minimum stem length before a prefix counts as a match, to avoid very short
// stems matching almost everything.
const MIN_PREFIX = 3;

// A [bracketed] span in the observation text becomes a shortcut that fills the
// filter input with the bracketed term — e.g. clicking [2025] filters to 2025.
const TAG_RE = /\[([^\[\]\n]+)\]/g;

const stemWord = (word) => ({
    pl: plStemmer(new lunr.Token(word)).toString(),
    en: enStemmer(new lunr.Token(word)).toString(),
});

const tokenize = (text) =>
    text
        .toLowerCase()
        .split(/[^0-9a-ząćęłńóśźż]+/i)
        .filter(Boolean);

// True when either stem is a prefix of the other (and long enough to be safe).
const sharedPrefix = (a, b) => {
    const min = Math.min(a.length, b.length);
    return min >= MIN_PREFIX && (a.startsWith(b) || b.startsWith(a));
};

// Replace every [bracketed] span in `root`'s text with a clickable link that
// calls `onTagClick(term)` with the text between the brackets.
const decorateTags = (root, onTagClick) => {
    // Collect matching text nodes first — mutating during the walk is unsafe.
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
            // Leave the meta line and any existing links untouched.
            if (node.parentElement.closest("a, .meta")) {
                return NodeFilter.FILTER_REJECT;
            }
            TAG_RE.lastIndex = 0;
            return TAG_RE.test(node.nodeValue)
                ? NodeFilter.FILTER_ACCEPT
                : NodeFilter.FILTER_REJECT;
        },
    });

    const textNodes = [];
    while (walker.nextNode()) {
        textNodes.push(walker.currentNode);
    }

    textNodes.forEach((textNode) => {
        const text = textNode.nodeValue;
        const fragment = document.createDocumentFragment();
        let lastIndex = 0;
        let match;

        TAG_RE.lastIndex = 0;
        while ((match = TAG_RE.exec(text)) !== null) {
            const [full, term] = match;

            if (match.index > lastIndex) {
                fragment.appendChild(
                    document.createTextNode(text.slice(lastIndex, match.index))
                );
            }

            const link = document.createElement("a");
            link.href = "#";
            link.className = "observation-tag";
            link.textContent = full; // keep the [brackets] visible
            link.addEventListener("click", (event) => {
                event.preventDefault();
                onTagClick(term.trim());
            });
            fragment.appendChild(link);

            lastIndex = match.index + full.length;
        }

        if (lastIndex < text.length) {
            fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
        }

        textNode.parentNode.replaceChild(fragment, textNode);
    });
};

const initObservationSearch = () => {
    const input = document.getElementById("observation-filter");

    // Only the observation list page has the filter input; bail everywhere else.
    if (!input) {
        return;
    }

    const articles = [
        ...document.querySelectorAll("article.observation[data-search]"),
    ];

    if (articles.length === 0) {
        return;
    }

    const counter = document.getElementById("observation-filter-count");

    // Pre-compute the stems for each article once.
    const indexed = articles.map((el) => {
        const stems = [];
        tokenize(el.dataset.search).forEach((token) => {
            const { pl, en } = stemWord(token);
            stems.push(pl, en);
        });
        return { el, stems, set: new Set(stems) };
    });

    const matchesWord = (doc, word) => {
        if (doc.set.has(word.pl) || doc.set.has(word.en)) {
            return true;
        }
        return doc.stems.some(
            (stem) => sharedPrefix(stem, word.pl) || sharedPrefix(stem, word.en)
        );
    };

    const setCount = (visible) => {
        if (!counter) {
            return;
        }
        counter.textContent =
            visible === null ? "" : `${visible} / ${articles.length}`;
    };

    const filter = () => {
        const words = tokenize(input.value).map(stemWord);

        if (words.length === 0) {
            indexed.forEach((doc) => {
                doc.el.style.display = "";
            });
            setCount(null);
            return;
        }

        let visible = 0;
        indexed.forEach((doc) => {
            const hit = words.every((word) => matchesWord(doc, word));
            doc.el.style.display = hit ? "" : "none";
            if (hit) {
                visible += 1;
            }
        });
        setCount(visible);
    };

    input.addEventListener("input", filter);

    // Wire up the [bracketed] tag shortcuts: clicking one fills the filter with
    // the bracketed term and re-runs the filter.
    const applyTag = (term) => {
        input.value = term;
        filter();
        input.focus({ preventScroll: true });
        input.scrollIntoView({ behavior: "smooth", block: "start" });
    };

    articles.forEach((article) => decorateTags(article, applyTag));
};

initObservationSearch();
