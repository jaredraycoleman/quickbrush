# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory to /app
WORKDIR /app

# Copy minimal web requirements for production
ADD ./requirements.web.txt /app/requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
ADD . /app

# Make port 80 available to the world outside this container
EXPOSE 80

# Run gunicorn when the container launches
# Use 2 workers (reduced from 4 to save memory)
CMD ["gunicorn", "app:app", "-b", "0.0.0.0:80", "--workers", "2", "--timeout", "120"]
