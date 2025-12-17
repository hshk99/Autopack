# Use an official Python runtime as a parent image
FROM python:3.11-slim as backend

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY ./src /app/src
COPY ./requirements.txt /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Run uvicorn server
CMD ["uvicorn", "src.autopack.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Stage for frontend
FROM node:20 as frontend

# Set the working directory in the container
WORKDIR /app

# Copy the package.json and package-lock.json from the correct frontend location
COPY ./src/autopack/dashboard/frontend/package.json /app/
COPY ./src/autopack/dashboard/frontend/package-lock.json* /app/

# Install frontend dependencies
RUN npm install

# Copy the rest of the frontend application code
COPY ./src/autopack/dashboard/frontend /app

# Build the frontend
RUN npm run build

# Stage for production
FROM nginx:alpine

# Copy built frontend from the previous stage
COPY --from=frontend /app/dist /usr/share/nginx/html

# Expose port 80
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
