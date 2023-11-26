# AftertimeBalance_BackEnd

i## Content
* Run locally
  * [Quickstart Windows]()


## Quickstart Windows

```commandline
git clone https://github.com/AftertimeORG/AftertimeBalance_backend.git
cd AftertimeBalance_backend
```

Install tool (optional)
```commandline
pip install poetry
poetry config virtualenvs.in-project true
??? poetry config virtualenvs.path .\.venv
```

Install libraries
```commandline
poetry install
```

Initial configuration of project (DEVELOPMENT VERSION, SQLite base)
```commandline
copy ./config/settings/dev_databases_template.py ./config/settings/dev_databases.py
copy ./.env_template ./.env
poetry run python manage.py init
```

First run DB configuration
```commandline
poetry run python manage.py migrate
poetry run python manage.py createsuperuser
```

Run the system
```commandline
poetry run python manage.py runserver
```


## Quickstart Ubuntu




## Quickstart


