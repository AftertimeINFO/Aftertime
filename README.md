# Aftertime


# Deployment

### Clone project
```
git clone https://github.com/AftertimeINFO/aftertime_prod.git
```

### Load submodules
```
cd aftertime_prod
git submodule init
git submodule update
```

### Initialize environment variables
#### Windows
```
copy .env.prod .env
```
#### Ubuntu
```
cp .env.prod .env
```

### Docker deploy
```
docker compose up -d
```