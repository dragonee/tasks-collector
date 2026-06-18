// Trip detail: a modal to add a note and/or a photo, plus drag-and-drop of an
// image onto the map/history column.
//
// One form, two endpoints chosen by whether a file is attached:
//   - no file  -> POST /trips/<id>/note/   (comment, form-encoded)
//   - has file -> presign -> direct-to-storage PUT -> POST /trips/<id>/photo/
//                 (the note text becomes the photo caption)
//
// Both return the re-rendered #trip-entries partial, which we swap in place and
// announce with `trip:entries-updated` so trip_map.js can re-index its list.
//
// Loaded only for the owner of an active trip (see trip_detail.html).

// Mirror the server-side allow-list (services/photos/keys.py); the server
// validates too, this is just a friendly message before any upload.
const SUPPORTED = ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'];

const modal = document.getElementById('trip-add-modal');

if (modal) {
    const storyId = modal.dataset.storyId;
    const form = modal.querySelector('.trip-add-form');
    const comment = form.querySelector('textarea[name=comment]');
    const fileInput = form.querySelector('input[type=file]');
    const nameLabel = form.querySelector('.trip-add-photo-name');
    const preview = form.querySelector('.trip-add-preview');
    const previewImg = preview ? preview.querySelector('img') : null;
    const removeBtn = preview ? preview.querySelector('.trip-add-preview-remove') : null;
    const status = form.querySelector('.trip-add-status');
    const submit = form.querySelector('.trip-add-submit');
    const defaultName = nameLabel ? nameLabel.textContent : '';
    let previewUrl = null;

    function csrfToken() {
        const el = document.body.querySelector('[name=csrfmiddlewaretoken]');
        return el ? el.value : '';
    }

    function setStatus(text, isError) {
        if (!status) {
            return;
        }
        status.textContent = text || '';
        status.classList.toggle('is-error', Boolean(isError));
    }

    // Reflect the chosen file in the label and a local preview. The preview is a
    // blob: object URL — shown straight from the browser, never uploaded here.
    function syncFile() {
        const file = fileInput.files[0];
        nameLabel.textContent = file ? file.name : defaultName;

        if (previewUrl) {
            URL.revokeObjectURL(previewUrl);
            previewUrl = null;
        }
        if (!preview) {
            return;
        }
        if (file) {
            previewUrl = URL.createObjectURL(file);
            // HEIC/HEIF won't decode in <img>; hide gracefully, keep the name.
            previewImg.onerror = () => {
                preview.hidden = true;
            };
            previewImg.src = previewUrl;
            preview.hidden = false;
        } else {
            previewImg.removeAttribute('src');
            preview.hidden = true;
        }
    }

    function openModal() {
        modal.hidden = false;
        document.body.classList.add('trip-add-open');
        comment.focus();
    }

    function closeModal() {
        modal.hidden = true;
        document.body.classList.remove('trip-add-open');
    }

    function resetForm() {
        form.reset();
        syncFile();
        setStatus('');
    }

    // --- open / close ---

    document.querySelectorAll('[data-trip-add-open]').forEach((btn) => {
        btn.addEventListener('click', openModal);
    });
    modal.querySelectorAll('[data-trip-add-close]').forEach((el) => {
        el.addEventListener('click', () => {
            closeModal();
            resetForm();
        });
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !modal.hidden) {
            closeModal();
            resetForm();
        }
    });

    fileInput.addEventListener('change', () => {
        syncFile();
        setStatus('');
    });

    if (removeBtn) {
        removeBtn.addEventListener('click', () => {
            fileInput.value = '';
            syncFile();
            setStatus('');
        });
    }

    // --- submit: note and/or photo ---

    function swapEntries(html) {
        const container = document.getElementById('trip-entries');
        if (container) {
            container.outerHTML = html;
            document.body.dispatchEvent(new CustomEvent('trip:entries-updated'));
        }
    }

    async function addNote(text) {
        const res = await fetch(`/trips/${storyId}/note/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': csrfToken(),
            },
            body: new URLSearchParams({ comment: text }).toString(),
        });
        if (!res.ok) {
            throw new Error(`add note failed (${res.status})`);
        }
        return res.text();
    }

    async function addPhoto(file, caption) {
        const contentType = file.type;
        if (!SUPPORTED.includes(contentType)) {
            throw new Error('Unsupported image type.');
        }

        const presign = await fetch(`/trips/${storyId}/photo/presign/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify({ content_type: contentType }),
        });
        if (!presign.ok) {
            throw new Error(`presign failed (${presign.status})`);
        }
        const { key, upload_url } = await presign.json();

        // Direct-to-storage PUT. The presigned URL carries its own auth, so no
        // CSRF/cookies; the signed Content-Type must match exactly.
        const put = await fetch(upload_url, {
            method: 'PUT',
            headers: { 'Content-Type': contentType },
            body: file,
        });
        if (!put.ok) {
            throw new Error(`upload failed (${put.status})`);
        }

        const confirm = await fetch(`/trips/${storyId}/photo/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify({ key, content_type: contentType, comment: caption }),
        });
        if (!confirm.ok) {
            throw new Error(`confirm failed (${confirm.status})`);
        }
        return confirm.text();
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const file = fileInput.files[0];
        const text = comment.value.trim();
        if (!file && !text) {
            setStatus('Write a note or add a photo.', true);
            return;
        }

        submit.disabled = true;
        try {
            setStatus(file ? 'Uploading…' : 'Saving…');
            const html = file
                ? await addPhoto(file, comment.value)
                : await addNote(comment.value);
            swapEntries(html);
            closeModal();
            resetForm();
        } catch (err) {
            setStatus(err.message || 'Something went wrong.', true);
        } finally {
            submit.disabled = false;
        }
    });

    // --- drag & drop an image onto the map / history column ---

    const dropZone = document.querySelector('.split-left');
    if (dropZone) {
        // .split-left is a generic layout class, so scope the positioning here
        // (for the absolute overlay) instead of in shared CSS.
        if (getComputedStyle(dropZone).position === 'static') {
            dropZone.style.position = 'relative';
        }

        const overlay = document.createElement('div');
        overlay.className = 'trip-drop-overlay';
        overlay.innerHTML =
            '<div class="trip-drop-inner">' +
            '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M12 3v12"/><path d="m17 8-5-5-5 5"/><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/></svg>' +
            '<span>Drop an image</span>' +
            '</div>';
        dropZone.appendChild(overlay);

        // dragenter/leave fire per child element; count depth so moving over the
        // map/entries doesn't flicker the overlay.
        let depth = 0;
        const draggingFiles = (e) =>
            e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files');

        dropZone.addEventListener('dragenter', (e) => {
            if (!draggingFiles(e)) {
                return;
            }
            e.preventDefault();
            depth += 1;
            overlay.classList.add('is-active');
        });
        dropZone.addEventListener('dragover', (e) => {
            if (!draggingFiles(e)) {
                return;
            }
            e.preventDefault();
            e.dataTransfer.dropEffect = 'copy';
        });
        dropZone.addEventListener('dragleave', (e) => {
            if (!draggingFiles(e)) {
                return;
            }
            depth -= 1;
            if (depth <= 0) {
                depth = 0;
                overlay.classList.remove('is-active');
            }
        });
        dropZone.addEventListener('drop', (e) => {
            if (!draggingFiles(e)) {
                return;
            }
            e.preventDefault();
            depth = 0;
            overlay.classList.remove('is-active');

            const file = Array.from(e.dataTransfer.files).find((f) =>
                f.type.startsWith('image/')
            );
            if (!file) {
                return;
            }
            const dt = new DataTransfer();
            dt.items.add(file);
            fileInput.files = dt.files;
            syncFile();
            setStatus('');
            openModal();
        });

        // A drop that misses the zone would otherwise navigate away to the file.
        window.addEventListener('dragover', (e) => {
            if (draggingFiles(e)) {
                e.preventDefault();
            }
        });
        window.addEventListener('drop', (e) => {
            if (draggingFiles(e)) {
                e.preventDefault();
            }
        });
    }
}
