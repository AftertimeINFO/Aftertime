# Aftertime


# Deployment

### Clone project with submodules
```
git clone --recurse-submodules https://github.com/AftertimeINFO/aftertime_prod.git
cd aftertime_prod
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