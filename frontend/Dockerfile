FROM node:20-alpine AS build

WORKDIR /app
ENV NODE_OPTIONS=--max-old-space-size=2048

COPY package.json yarn.lock* ./
RUN yarn install --network-timeout 600000

COPY . .

# Same-origin by default (empty) -> API calls go to "/api", proxied by the gateway nginx.
ARG REACT_APP_BACKEND_URL=""
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

RUN yarn build

FROM nginx:alpine
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/app.conf
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 80
