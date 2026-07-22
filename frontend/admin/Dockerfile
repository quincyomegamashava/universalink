FROM node:22-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM alpine:3.20
WORKDIR /output
COPY --from=build /app/dist /tmp/dist
CMD ["sh", "-c", "rm -rf /output/* && cp -a /tmp/dist/. /output/ && echo 'Admin assets synced' && sleep infinity"]
