FROM node:22-alpine

WORKDIR /app

# npm ci installs exactly what the lockfile pins, so the image matches CI.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
