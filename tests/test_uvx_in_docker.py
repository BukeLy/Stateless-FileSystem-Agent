"""Test uvx availability in AWS Lambda Python 3.12 ARM64 container.

This script tests different methods to make uvx command available:
1. Symlink: ln -s /usr/local/bin/uv /usr/local/bin/uvx
2. curl install: curl -LsSf https://astral.sh/uv/install.sh | sh
3. COPY both uv and uvx from official image
"""

import subprocess
import tempfile
from pathlib import Path
import sys


def create_test_dockerfile(method: str) -> str:
    """Create a Dockerfile for testing specific uvx installation method."""

    base = """FROM public.ecr.aws/lambda/python:3.12-arm64

# Test different uvx installation methods
"""

    methods = {
        "symlink": """# Method 1: Copy uv and create symlink to uvx
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN ln -s /usr/local/bin/uv /usr/local/bin/uvx
""",

        "curl": """# Method 2: Use official install script (installs both uv and uvx)
# Install tar and gzip (required by install script)
RUN dnf install -y tar gzip
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:${PATH}"
""",

        "copy_both_fallback": """# Method 3: Try to copy uvx, fallback to symlink
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN if [ -f /uvx ]; then cp /uvx /usr/local/bin/uvx; else ln -s /usr/local/bin/uv /usr/local/bin/uvx; fi
""",
    }

    test_cmd = """
# Verify installation
RUN ls -la /usr/local/bin/uv* && uv --version
RUN ls -la /usr/local/bin/uvx && uvx --version

# Test uvx can execute help
RUN uvx --help

CMD ["/bin/bash"]
"""

    return base + methods[method] + test_cmd


def test_uvx_method(method: str) -> tuple[bool, str, str]:
    """Test a specific uvx installation method.

    Returns:
        (success, stdout, stderr)
    """
    print(f"\n{'='*60}")
    print(f"Testing method: {method}")
    print('='*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        dockerfile = tmppath / "Dockerfile"

        # Create Dockerfile
        content = create_test_dockerfile(method)
        dockerfile.write_text(content)
        print(f"\nDockerfile content:\n{content}")

        # Build image
        image_tag = f"test-uvx-{method}:latest"
        print(f"\nBuilding image: {image_tag}")

        try:
            # Build with progress output
            result = subprocess.run(
                ["docker", "build", "-t", image_tag, "-f", str(dockerfile), "."],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=300
            )

            stdout = result.stdout
            stderr = result.stderr

            if result.returncode != 0:
                print(f"❌ Build failed!")
                print(f"STDOUT:\n{stdout}")
                print(f"STDERR:\n{stderr}")
                return False, stdout, stderr

            print(f"✅ Build successful!")

            # Test uvx command in the container (override Lambda entrypoint)
            print(f"\nTesting uvx command execution...")
            test_result = subprocess.run(
                ["docker", "run", "--rm", "--entrypoint", "/bin/bash",
                 image_tag, "-c",
                 "uvx --version && echo '---' && uvx --help"],
                capture_output=True,
                text=True,
                timeout=60
            )

            print(f"Command output:\n{test_result.stdout}")

            if test_result.returncode != 0:
                print(f"❌ uvx execution failed!")
                print(f"STDERR:\n{test_result.stderr}")
                return False, stdout + "\n" + test_result.stdout, stderr + "\n" + test_result.stderr

            print(f"✅ uvx command works!")

            # Cleanup image
            subprocess.run(["docker", "rmi", image_tag],
                         capture_output=True, timeout=30)

            return True, stdout + "\n" + test_result.stdout, stderr

        except subprocess.TimeoutExpired:
            print(f"❌ Timeout!")
            return False, "", "Timeout during build or test"
        except Exception as e:
            print(f"❌ Error: {e}")
            return False, "", str(e)


def main():
    """Run all tests and report results."""
    print("="*60)
    print("Testing uvx availability in AWS Lambda container")
    print("="*60)

    methods = ["symlink", "curl", "copy_both_fallback"]
    results = {}

    for method in methods:
        success, stdout, stderr = test_uvx_method(method)
        results[method] = {
            "success": success,
            "stdout": stdout,
            "stderr": stderr
        }

    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    for method, result in results.items():
        status = "✅ SUCCESS" if result["success"] else "❌ FAILED"
        print(f"{method:15s}: {status}")

    # Print recommendation
    print("\n" + "="*60)
    print("RECOMMENDATION")
    print("="*60)

    successful_methods = [m for m, r in results.items() if r["success"]]

    if not successful_methods:
        print("❌ No method succeeded. Check Docker availability and network.")
        return 1

    # Prefer symlink (simplest and fastest)
    if "symlink" in successful_methods:
        print("""✅ Use symlink method (simplest and fastest):

Add to Dockerfile after copying uv:
    RUN ln -s /usr/local/bin/uv /usr/local/bin/uvx

Complete lines:
    COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
    RUN ln -s /usr/local/bin/uv /usr/local/bin/uvx
""")
    elif "curl" in successful_methods:
        print("""✅ Use curl install method:

Replace current uv installation with:
    RUN curl -LsSf https://astral.sh/uv/install.sh | sh
    ENV PATH="/root/.cargo/bin:${PATH}"
""")
    elif "copy_both_fallback" in successful_methods:
        print("""✅ Use copy_both_fallback method:

Replace current uv installation with:
    COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
    RUN if [ -f /uvx ]; then cp /uvx /usr/local/bin/uvx; else ln -s /usr/local/bin/uv /usr/local/bin/uvx; fi
""")

    return 0


if __name__ == "__main__":
    sys.exit(main())
