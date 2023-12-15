from io import BytesIO, StringIO
import docker
import tempfile
import os

def run_python_script(python_code, dependencies=[]):
    # Create a temporary directory to hold the Python script
    with tempfile.TemporaryDirectory() as temp_dir:
        script_path = os.path.join(temp_dir, "script.py")

        # Write the Python code to a script file
        with open(script_path, 'w') as file:
            file.write(python_code)

        # Create a Docker client
        client = docker.from_env()

        # Define the Dockerfile as a multi-line string
        dockerfile = f"""
        FROM python:3.12-slim
        COPY . /app
        WORKDIR /app
        """
        if len(dependencies) > 0:
            dockerfile += f"""RUN pip install {' '.join(dependencies)}"""
        dockerfile += f"""
        CMD ["python", "script.py"]
        """

        # Send the Dockerfile to the Docker daemon
        image, _ = client.images.build(path=temp_dir, fileobj=BytesIO(dockerfile.encode('utf-8')), rm=True, tag="python_script_runner")

        # Run the container
        container = client.containers.run("python_script_runner", detach=True, volumes={temp_dir: {'bind': '/app', 'mode': 'rw'}})

        # Wait for the container to finish
        container.wait()

        # Retrieve the results
        output = container.logs()
        container.remove()
        return output.decode('utf-8')
    
if __name__ == "__main__":
    python_code = """
import os
import numpy as np
np.random.seed(42)
print(np.random.randint(0, 100, 10))
    """
    print(run_python_script(python_code, ["numpy"]), end="")
    