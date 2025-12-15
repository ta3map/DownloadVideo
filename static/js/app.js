// Глобальные переменные
let currentTaskId = null;
let progressEventSource = null;
let currentFetchTaskId = null;

// Элементы DOM
const urlInput = document.getElementById('url-input');
const downloadFolderInput = document.getElementById('download-folder');
const audioOnlyCheckbox = document.getElementById('audio-only');
const fetchFormatsBtn = document.getElementById('fetch-formats-btn');
const formatsSection = document.getElementById('formats-section');
const formatsSelect = document.getElementById('formats-select');
const downloadBtn = document.getElementById('download-btn');
const pauseBtn = document.getElementById('pause-btn');
const stopBtn = document.getElementById('stop-btn');
const progressBar = document.getElementById('progress-bar');
const progressText = document.getElementById('progress-text');
const statusMessage = document.getElementById('status-message');
const downloadsList = document.getElementById('downloads-list');

// Отправка ошибки на бэкенд
async function logErrorToBackend(type, message, stack, timestamp) {
    try {
        await fetch('/api/log-error', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                type: type,
                message: message,
                stack: stack,
                timestamp: timestamp
            })
        });
    } catch (error) {
        // Если не удалось отправить, хотя бы выводим в консоль
        console.error('Failed to log error to backend:', error);
    }
}

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    setupErrorHandling();
    loadConfig();
    loadDownloads();
    setupEventListeners();
});

// Настройка глобальной обработки ошибок
function setupErrorHandling() {
    // Обработка необработанных ошибок
    window.addEventListener('error', (event) => {
        logErrorToBackend('error', event.message, event.error?.stack || '', new Date().toISOString());
    });
    
    // Обработка необработанных промисов
    window.addEventListener('unhandledrejection', (event) => {
        logErrorToBackend('unhandledrejection', event.reason?.message || String(event.reason), event.reason?.stack || '', new Date().toISOString());
    });
    
    // Перехват console.error
    const originalConsoleError = console.error;
    console.error = function(...args) {
        originalConsoleError.apply(console, args);
        const message = args.map(arg => {
            if (typeof arg === 'object') {
                try {
                    return JSON.stringify(arg);
                } catch (e) {
                    return String(arg);
                }
            }
            return String(arg);
        }).join(' ');
        logErrorToBackend('console.error', message, '', new Date().toISOString());
    };
}

// Загрузка конфигурации
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        const data = await response.json();
        downloadFolderInput.value = data.download_folder || 'Не указана';
    } catch (error) {
        console.error('Ошибка загрузки конфигурации:', error);
        logErrorToBackend('loadConfig', error.message, error.stack, new Date().toISOString());
    }
}

// Настройка обработчиков событий
function setupEventListeners() {
    fetchFormatsBtn.addEventListener('click', handleFetchFormats);
    downloadBtn.addEventListener('click', handleDownload);
    pauseBtn.addEventListener('click', handlePause);
    stopBtn.addEventListener('click', handleStop);
    audioOnlyCheckbox.addEventListener('change', handleAudioOnlyChange);
    formatsSelect.addEventListener('change', () => {
        downloadBtn.disabled = false;
    });
}

// Обработка изменения чекбокса "Только аудио"
function handleAudioOnlyChange() {
    if (audioOnlyCheckbox.checked) {
        formatsSection.style.display = 'none';
        downloadBtn.disabled = false;
    } else {
        formatsSection.style.display = 'block';
        downloadBtn.disabled = formatsSelect.selectedIndex === -1;
    }
}

// Получение форматов
async function handleFetchFormats() {
    const url = urlInput.value.trim();
    if (!url) {
        showStatus('Введите URL видео!', 'error');
        return;
    }

    if (audioOnlyCheckbox.checked) {
        showStatus('Режим "Только аудио" выбран. Форматы не нужны.', 'info');
        return;
    }

    fetchFormatsBtn.disabled = true;
    showStatus('Получение форматов...', 'info');

    try {
        const response = await fetch('/api/fetch-formats', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ url })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Ошибка получения форматов');
        }

        const data = await response.json();
        currentFetchTaskId = data.task_id;

        // Проверяем результат каждые 500мс
        checkFormatsResult();
    } catch (error) {
        showStatus('Ошибка: ' + error.message, 'error');
        fetchFormatsBtn.disabled = false;
        logErrorToBackend('fetchFormats', error.message, error.stack, new Date().toISOString());
    }
}

// Проверка результата получения форматов
async function checkFormatsResult() {
    if (!currentFetchTaskId) return;

    try {
        const response = await fetch(`/api/get-formats/${currentFetchTaskId}`);
        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        if (data.formats) {
            // Форматы получены
            formatsSelect.innerHTML = '';
            data.formats.forEach((fmt, index) => {
                const option = document.createElement('option');
                const hasFfmpeg = fmt.format && typeof fmt.format === 'string' && fmt.format.includes('+');
                const label = `${fmt.resolution || 'audio'} | ${fmt.ext} | ${fmt.format_note || ''}${hasFfmpeg ? ' +ffmpeg' : ''}`;
                option.textContent = label;
                option.value = fmt.format_id;
                formatsSelect.appendChild(option);
            });
            formatsSection.style.display = 'block';
            showStatus(`Форматы получены для: ${data.title || 'видео'}`, 'success');
            fetchFormatsBtn.disabled = false;
            currentFetchTaskId = null;
        } else if (data.status === 'fetching') {
            // Еще загружается
            setTimeout(checkFormatsResult, 500);
        }
    } catch (error) {
        showStatus('Ошибка: ' + error.message, 'error');
        fetchFormatsBtn.disabled = false;
        currentFetchTaskId = null;
        logErrorToBackend('checkFormatsResult', error.message, error.stack, new Date().toISOString());
    }
}

// Запуск скачивания
async function handleDownload() {
    const url = urlInput.value.trim();
    if (!url) {
        showStatus('Введите URL видео!', 'error');
        return;
    }

    const audioOnly = audioOnlyCheckbox.checked;
    let formatId = null;

    if (!audioOnly) {
        formatId = formatsSelect.value;
        if (!formatId) {
            showStatus('Выберите формат!', 'error');
            return;
        }
    }

    downloadBtn.disabled = true;
    pauseBtn.disabled = false;
    stopBtn.disabled = false;
    fetchFormatsBtn.disabled = true;
    urlInput.disabled = true;
    audioOnlyCheckbox.disabled = true;
    formatsSelect.disabled = true;

    showStatus('Запуск скачивания...', 'info');
    resetProgress();

    try {
        const response = await fetch('/api/download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                url,
                format_id: formatId,
                audio_only: audioOnly,
                download_folder: downloadFolderInput.value
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Ошибка запуска скачивания');
        }

        const data = await response.json();
        currentTaskId = data.task_id;

        // Подключаемся к SSE потоку прогресса
        connectProgressStream();
    } catch (error) {
        showStatus('Ошибка: ' + error.message, 'error');
        resetControls();
        logErrorToBackend('handleDownload', error.message, error.stack, new Date().toISOString());
    }
}

// Подключение к SSE потоку прогресса
function connectProgressStream() {
    if (progressEventSource) {
        progressEventSource.close();
    }

    progressEventSource = new EventSource(`/api/progress/${currentTaskId}`);

    progressEventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);

            if (data.error) {
                showStatus('Ошибка: ' + data.error, 'error');
                logErrorToBackend('SSE_message_error', data.error, '', new Date().toISOString());
                progressEventSource.close();
                resetControls();
                return;
            }

        updateProgress(data.progress || 0);

        if (data.status === 'finished') {
            showStatus('Скачивание завершено!', 'success');
            progressEventSource.close();
            resetControls();
            loadDownloads();
        } else if (data.status === 'error') {
            const errorMsg = data.error || 'Неизвестная ошибка';
            showStatus('Ошибка скачивания: ' + errorMsg, 'error');
            logErrorToBackend('download_error', errorMsg, '', new Date().toISOString());
            progressEventSource.close();
            resetControls();
        } else if (data.status === 'cancelled') {
            showStatus('Скачивание отменено', 'info');
            progressEventSource.close();
            resetControls();
        } else if (data.status === 'paused') {
            pauseBtn.textContent = 'Продолжить';
            showStatus('Скачивание приостановлено', 'info');
        } else if (data.status === 'downloading') {
            pauseBtn.textContent = 'Пауза';
        }
        } catch (error) {
            logErrorToBackend('SSE_parse_error', error.message, error.stack, new Date().toISOString());
            console.error('Ошибка парсинга SSE данных:', error, event.data);
        }
    };

    progressEventSource.onerror = (error) => {
        logErrorToBackend('SSE_error', 'EventSource error', error?.stack || '', new Date().toISOString());
        progressEventSource.close();
    };
}

// Обновление прогресса
function updateProgress(percent) {
    progressBar.style.width = percent + '%';
    progressText.textContent = Math.round(percent) + '%';
}

// Сброс прогресса
function resetProgress() {
    updateProgress(0);
}

// Пауза/продолжение
async function handlePause() {
    if (!currentTaskId) return;

    const isPaused = pauseBtn.textContent === 'Продолжить';
    const endpoint = isPaused ? 'resume' : 'pause';

    try {
        const response = await fetch(`/api/${endpoint}/${currentTaskId}`, {
            method: 'POST'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Ошибка');
        }

        if (isPaused) {
            pauseBtn.textContent = 'Пауза';
            showStatus('Скачивание возобновлено', 'info');
        } else {
            pauseBtn.textContent = 'Продолжить';
            showStatus('Скачивание приостановлено', 'info');
        }
    } catch (error) {
        showStatus('Ошибка: ' + error.message, 'error');
        logErrorToBackend('handlePause', error.message, error.stack, new Date().toISOString());
    }
}

// Остановка
async function handleStop() {
    if (!currentTaskId) return;

    try {
        const response = await fetch(`/api/stop/${currentTaskId}`, {
            method: 'POST'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Ошибка');
        }

        if (progressEventSource) {
            progressEventSource.close();
        }

        showStatus('Скачивание остановлено', 'info');
        resetControls();
    } catch (error) {
        showStatus('Ошибка: ' + error.message, 'error');
        logErrorToBackend('handleStop', error.message, error.stack, new Date().toISOString());
    }
}

// Сброс элементов управления
function resetControls() {
    downloadBtn.disabled = false;
    pauseBtn.disabled = true;
    stopBtn.disabled = true;
    fetchFormatsBtn.disabled = false;
    urlInput.disabled = false;
    audioOnlyCheckbox.disabled = false;
    formatsSelect.disabled = false;
    pauseBtn.textContent = 'Пауза';
    currentTaskId = null;
}

// Показать статус
function showStatus(message, type) {
    statusMessage.textContent = message;
    statusMessage.className = 'status-message ' + type;
    statusMessage.style.display = 'block';

    if (type === 'success' || type === 'info') {
        setTimeout(() => {
            statusMessage.style.display = 'none';
        }, 5000);
    }
}

// Загрузка списка скачанных файлов
async function loadDownloads() {
    try {
        const response = await fetch('/api/downloads');
        const data = await response.json();

        if (data.error) {
            console.error('Ошибка загрузки файлов:', data.error);
            return;
        }

        downloadsList.innerHTML = '';

        if (data.files && data.files.length > 0) {
            data.files.forEach(file => {
                const item = document.createElement('div');
                item.className = 'download-item';

                const info = document.createElement('div');
                info.className = 'download-item-info';

                const name = document.createElement('div');
                name.className = 'download-item-name';
                name.textContent = file.name;

                const size = document.createElement('div');
                size.className = 'download-item-size';
                size.textContent = formatFileSize(file.size);

                info.appendChild(name);
                info.appendChild(size);

                const btn = document.createElement('button');
                btn.className = 'download-item-btn';
                btn.textContent = 'Скачать';
                btn.addEventListener('click', () => {
                    window.open(`/api/download-file/${encodeURIComponent(file.name)}`, '_blank');
                });

                item.appendChild(info);
                item.appendChild(btn);
                downloadsList.appendChild(item);
            });
        } else {
            downloadsList.innerHTML = '<p style="color: #718096; text-align: center;">Нет скачанных файлов</p>';
        }
    } catch (error) {
        console.error('Ошибка загрузки файлов:', error);
        logErrorToBackend('loadDownloads', error.message, error.stack, new Date().toISOString());
    }
}

// Форматирование размера файла
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

