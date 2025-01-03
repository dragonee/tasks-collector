// App code-base initialistaion goes here.

// Load app-wide styles. Those will affect
// every component. For Vue-component-specific styles
// see scoped CSS.
require('./app.scss')

const nodeList = document.querySelectorAll(
    'article.observation'
);

[...nodeList].forEach((observation) => {
    const link = document.createElement('span');
    link.classList.add("observation-hide");

    link.addEventListener('click', () => {
        observation.classList.toggle('open');
    })

    observation.appendChild(link);
});

const journalAddedEvents = document.querySelectorAll('.event-content.journal-added');

const addBreakthroughButtonListener = (event, habitName) => {
    const button = event.querySelector('.add-breakthrough-button');
    const form = event.querySelector('.habit-form');

    button.addEventListener('click', () => {
        form.classList.remove('hidden');
        form.querySelector('form').classList.remove('hidden');

        const textField = form.querySelector('[name=text]');
        textField.value = habitName + ' ';
        textField.focus();
        button.classList.add('hidden');
    })
};

[...journalAddedEvents].forEach((event) => addBreakthroughButtonListener(event, '#breakthrough'));

const onBreakthroughAdded = (element) => {
    const closestJournalAdded = element.closest('.journal-added');

    const form = closestJournalAdded.querySelector('.habit-form');
    const button = closestJournalAdded.querySelector('.add-breakthrough-button');
    const result = closestJournalAdded.querySelector('.result-ok');
    
    setTimeout(() => {
        result.remove();

        addBreakthroughButtonListener(closestJournalAdded);

        form.classList.add('hidden');
        button.classList.remove('hidden');
        element.remove();
    }, 2000);
}

window.onBreakthroughAdded = onBreakthroughAdded;

document.querySelectorAll('.breakthrough textarea').forEach((textarea) => {
    textarea.addEventListener('input', () => {
        textarea.style.height = 'auto';
        textarea.style.height = `${textarea.scrollHeight}px`;
    });

    textarea.dispatchEvent(new Event('input'));
});


document.querySelectorAll('.breakthrough-outcome').forEach((outcome) => {
    const button = outcome.querySelector('button.accordion');
    const textarea = outcome.querySelectorAll('textarea');

    if (!button) {
        return;
    }
    
    button.addEventListener('click', (event) => {
        outcome.classList.toggle('open');
        event.stopPropagation();
        event.preventDefault();

        textarea.forEach((textarea) => {
            textarea.dispatchEvent(new Event('input'));
        });
    });

    const confidenceLevel = outcome.querySelector('.breakthrough-outcome-confidence input[type="range"]');
    const confidenceLevelValue = outcome.querySelector('.breakthrough-outcome-name .confidence-level');

    if (!confidenceLevel) {
        return;
    }

    confidenceLevel.addEventListener('input', () => {
        if (confidenceLevel.value === '0') {
            confidenceLevelValue.textContent = 'by';
        } else {
            confidenceLevelValue.textContent = `${confidenceLevel.value}%`;
        }
    });
});


const setUrlParameter = (parameter, value) => {
    const url = new URL(window.location.href);
    url.searchParams.set(parameter, value);
    window.location.href = url.toString();
}

window.setUrlParameter = setUrlParameter;
