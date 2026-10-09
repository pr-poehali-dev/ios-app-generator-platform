# Установка runner на Windows 10/11 (из России)

Runner скачивает коммит с GitHub, устанавливает зависимости и собирает проект в изолированном Docker-контейнере. Он сам обращается в кабинет, входящие порты открывать не нужно.

Рекомендуемая схема: **WSL2 + Ubuntu + Docker Engine внутри WSL, runner запускается там же.** Docker Desktop не нужен. Причины: не зависит от лицензии и регистрации Docker Desktop, нет проблем с путями Windows и правами файлов, диск WSL быстрее для `node_modules`.

## 1. Проверьте компьютер
- Windows 10 22H2 (сборка 19045) или новее, либо Windows 11.
- Виртуализация включена в BIOS (Intel VT-x / AMD-V). Проверка: Диспетчер задач → Производительность → ЦП → «Виртуализация: включено».
- 16 ГБ ОЗУ и 30 ГБ свободно у вас есть. Этого достаточно.

## 2. Установите WSL2 и Ubuntu
PowerShell от имени администратора:

    wsl --install -d Ubuntu

Перезагрузите компьютер, при первом запуске Ubuntu задайте имя пользователя и пароль (это пароль Linux, не Windows). Проверка:

    wsl -l -v

Версия Ubuntu должна быть 2. Если команда не скачивает Ubuntu (Microsoft Store недоступен), установите дистрибутив из файла `.appx`/`.wsl`, скачанного с официального сайта Microsoft, или обновите WSL: `wsl --update`.

## 3. Установите Docker Engine в Ubuntu
В терминале Ubuntu:

    sudo apt-get update
    sudo apt-get install -y ca-certificates curl gnupg python3
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io
    sudo usermod -aG docker $USER

Закройте окно Ubuntu и откройте заново. Если `download.docker.com` недоступен из вашей сети, установите пакет `docker.io` из репозитория Ubuntu: `sudo apt-get install -y docker.io`.

Если после установки Docker не запущен: `sudo service docker start` (в современных WSL автозапуск включён через systemd).

Проверка:

    docker version

## 4. Проверьте доступ к образам
    docker pull node:20-bookworm-slim

Если команда не проходит (таймаут, 403), доступ к Docker Hub с вашего адреса ограничен. Подключите зеркало. Создайте файл `/etc/docker/daemon.json` (`sudo nano /etc/docker/daemon.json`):

    { "registry-mirrors": ["https://dh-mirror.gitverse.ru", "https://mirror.gcr.io"] }

Затем `sudo service docker restart` и повторите `docker pull`. Зеркала сторонние и могут меняться или пропасть: проверяйте актуальность в документации поставщика. Для сборки лучше брать образ `node` из проверенного вами источника.

Заранее скачайте нужные версии, чтобы первый запуск не ждал: `docker pull node:20-bookworm-slim`.

## 5. Получите runner и ключ
1. В кабинете откройте проект → «Сборка» → «Создать ключ». Ключ показывается один раз, скопируйте его.
2. Скопируйте папку `runner` из проекта в домашнюю папку Ubuntu (например `~/runner`), не работайте из `/mnt/c`: так медленнее.
3. В папке создайте `config.json` по образцу `config.example.json`:
   - `cabinet_url` — адрес функции кабинета (из `backend/func2url.json`, ключ `studio`).
   - `runner_key` — ключ из кабинета.
   - `github_token` — только для приватных репозиториев: fine-grained токен, Contents: Read-only, на один репозиторий. Токен хранится только в этом файле на вашем компьютере.
4. Защитите файл: `chmod 600 config.json`.

## 6. Проверьте и запустите
    cd ~/runner
    python3 runner.py --check

Ожидается: Docker работает, кабинет доступен, ключ принят. Затем:

    python3 runner.py

Runner ждёт задания и для каждого показывает репозиторий, коммит и команды и спрашивает `[y/N]`. Одновременно подтверждение даёте в кабинете (кнопка «Новая сборка»).

## Что делает runner для безопасности
- Скачивает архив строго по SHA и сверяет его с коммитом; отклоняет архив с `../`, ссылками и «бомбами».
- Запускает только команды из белого списка: `npm ci`, `npm install`, `pnpm install --frozen-lockfile`, затем `npm|pnpm run build`.
- Установка по умолчанию с `--ignore-scripts` (скрипты зависимостей выключены, пока вы явно не разрешите).
- Контейнер: без привилегий (`--cap-drop ALL`, `no-new-privileges`), файловая система только для чтения, лимиты памяти, процессов и CPU, один том с проектом, без Docker socket и домашней папки.
- **Сборка идёт без сети** (`--network none`). Установка зависимостей идёт с сетью — иначе npm не скачает пакеты.
- Журнал очищается от токенов, паролей и ключей до отправки в кабинет.
- В контейнер не передаются ваши переменные окружения и production-секреты.

## Ограничения (честно)
- Docker снижает риск, но не гарантирует безопасность: установка зависимостей с включёнными скриптами исполняет чужой код с доступом в сеть. Подключайте только свои репозитории.
- Если сборке нужны переменные окружения (например `VITE_*`), сейчас они не передаются, и такая сборка может не пройти. Это отдельный шаг.
- Настоящие лимиты Docker в WSL ограничены ресурсами, выделенными WSL (файл `%UserProfile%\.wslconfig`).
- Проект с несколькими пакетами (монорепозиторий) не поддерживается: сборка идёт из корня.
