FROM node as build
WORKDIR /app
COPY package.json .
RUN npm install --force
COPY . .
EXPOSE 3000
RUN npm run build
FROM nginx
COPY --from=build /app/build /usr/share/nginx/html

# CMD ["npm", "start"]