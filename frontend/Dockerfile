FROM node:20-alpine

WORKDIR /app

# Install dependencies first (cache layer)
COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 5173

# --host 0.0.0.0 is required so the port is accessible from outside the container
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
