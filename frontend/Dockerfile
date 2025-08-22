FROM node:20-alpine

WORKDIR /app

# Install deps early for better caching
COPY frontend/package*.json ./
RUN npm ci || npm install

# Project files (overridden by volume in dev)
COPY frontend ./

EXPOSE 3000
CMD ["npm", "run", "dev", "--", "-p", "3000", "--host", "0.0.0.0"]