FROM node as build
WORKDIR /app
COPY package.json .
RUN npm install --force
COPY . .
ARG REACT_APP_API_SERVER_FRONT
ENV REACT_APP_API_SERVER_FRONT $REACT_APP_API_SERVER_FRONT
EXPOSE 3000
RUN npm run build
FROM nginx
COPY --from=build /app/build /usr/share/nginx/html
ENTRYPOINT ["nginx", "-g", "daemon off;"]