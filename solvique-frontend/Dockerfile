# Stage 1: Build Angular application
FROM node:20-alpine AS build
WORKDIR /app

# Install dependencies first for Docker layer caching
COPY package*.json ./
RUN npm ci

# Copy application code and build production bundle
COPY . .
RUN npm run build -- --configuration production

# Stage 2: Serve application via Nginx
FROM nginx:alpine
ENV PORT=8080

# Clean default html
RUN rm -rf /usr/share/nginx/html/*

# Copy built browser assets to nginx html
COPY --from=build /app/dist/solvique_frontend/browser /usr/share/nginx/html

# Copy nginx template with $PORT substitution support
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
