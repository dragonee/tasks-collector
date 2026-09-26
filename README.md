# Tasks Collector 

My own approach to keep track of my life.

## Installation

> Note: if you are a lazy hog, please scroll down to the "Docker" section.

### Prerequisites

#### Database

```
createuser -P tasks
createdb -E utf8 tasks -O tasks
```

#### Node
To install nvm use official guide https://github.com/creationix/nvm#install--update-script.

If you are using zsh shell you can use one of those guides to make nvm work inside shell:

* https://github.com/robbyrussell/oh-my-zsh/tree/master/plugins/nvm
* https://github.com/lukechilds/zsh-nvm

After setup nvm you can use this command to install specific node package
```
nvm install 10
```

To choose one of installed nvm version type:
```
$ nvm use 10
Now using node v10.10.0 (npm v6.4.1)
```

### Setup

#### Python
```
python3 -m venv env
source env/bin/activate
pip install -r requirements/local.txt // or requirements/dist.txt in production environment
```

### JS Stack
```
npm install
npm run dev // or npm run build for one-time compilation
```

If you want to build production assets, use:
```
npm run build-dist
```

#### Django

Provided that `editor` symlinks to vim, emacs or nano:

```
make config
./manage.py migrate
./manage.py createsuperuser
./manage.py runserver
```

Alternatively, copy the `tasks/settings/db.py.base` to
`tasks/settings/db.py` and modify it to your needs,
then run the rest of the commands.

## Production deployment

Every push to `main` (except Android, CLI and docs-only changes) runs
`.github/workflows/deploy.yml`, which:

1. Builds `docker/production/Dockerfile` and pushes it to
   `ghcr.io/dragonee/tasks-collector`, tagged with the commit SHA and `latest`.
2. SSHes into the server, pulls that image, runs `migrate` in a throwaway
   container, and replaces two containers started from the same image:
   `tasks-app` (gunicorn on `127.0.0.1:9422`, static files served by
   WhiteNoise) and `tasks-celery` (the Celery worker).

Both containers run with `--network host` and read their configuration from
`$DEPLOY_PATH/.env` - see `docker/production/.env.example`. The workflow uses
the `DEPLOY_HOST`, `DEPLOY_PORT`, `DEPLOY_USER`, `DEPLOY_KEY` and
`DEPLOY_PATH` repository secrets.

Useful commands on the server:

```
docker logs -f tasks-app
docker exec -it tasks-app python manage.dist.py shell
```

### Moving the server over to Docker

One-time steps, in this order, so the site stays up throughout:

1. Install Docker and add `DEPLOY_USER` to the `docker` group.
2. Create `$DEPLOY_PATH/.env` from `docker/production/.env.example`, carrying
   the values over from `tasks/settings/db.py`, `email.py` and `aws.py`. Use a
   freshly generated `SECRET_KEY` rather than the one in `base.py`, which is
   public. That logs web sessions out once; API tokens keep working.
3. Make Postgres accept password logins over TCP on `127.0.0.1` for the
   `DATABASE_URL` user (`pg_hba.conf`) - the container can't use peer auth.
4. Run the deploy workflow. The containers start next to the supervisor
   gunicorn, which keeps serving on its unix socket. Check
   `curl http://127.0.0.1:9422/health/` on the server.
5. Point nginx at the container - `proxy_pass http://127.0.0.1:9422;` in place
   of the gunicorn socket - and remove any `location /static/` alias, since
   the app now serves its own static files. Reload nginx.
6. Stop and remove the `pbtasks` supervisor program, and the Celery one if
   there is any.

## Docker

### Prerequisites

To run this project in dockerized development environment the following
dependencies must be present in the system:

* `docker` (18.06.0+)
* `docker-compose` (1.22.0+)

### Running the project in development mode

This project supports dockerized development environment, so you
actually don't need to do any of the above steps. To run the project in
dockerized mode enter the `docker/development` directory and run:

```
docker-compose up
```

The application will be available at `http://localhost:8000`. The
database will be spawned, the migrations will be run automatically, all
deps installed (for both Python and JS) and the code will be
automatically reloaded when changes occur (for both assets and backend code).

### Running commands in the container

To run commands in the running container (for instance: installing new
packages, running tests, running Django commands etc.) please run in the
separate terminal window (while `docker-compose up` is running) the
following command:

```
docker-compose exec tasks-backend bash
```

This will start interactive `bash` session that will allow running all
the commands within running container.

### Getting the database dump

First, log in to the server and run:

```
sudo -u postgres pg_dump "$1" > "$1"-`date '+%Y-%m-%d_%H%M'`.sql
```

Then, copy the dump file to the local machine:

```
scp user@server:~/'*.sql' ~/databases
docker-compose exec tasks-db psql tasks -U tasks -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
docker-compose exec -T tasks-db psql tasks -U tasks < ~/databases/tasks-[...].sql
```
