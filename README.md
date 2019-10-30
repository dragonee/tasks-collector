# Tasks

A template for projects used in Makimo.

## Installation

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
npm run watch // or npm run build for one-time compilation
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

### Notes for deploy

Provided that `editor` symlinks to actual editor:
```
make deployconfig
```

Alternatively, copy the `tasks/settings/email.py.base` to
`tasks/settings/email.py` and modify it to your needs,
then run the rest of the commands.

1. Ensure that `DJANGODIR` in `bin/gunicorn.base` is proper.
2. Ensure that paths in `webpack-stats.dist.json` are proper (path is
configured in `package.json`).


#### More information
This project was created using `django-template` tool.

For more information, see:
https://bitbucket.org/makimo/django-template/src/master/.
If you find a bug, create an issue as a subtask of IWM-47.
