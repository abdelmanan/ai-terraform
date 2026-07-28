import re


class TerraformParser:

    def parse(self, response: str):

        files = {}

        pattern = r"###\s*(.*?)\nBEGIN_(?:TERRAFORM|TEXT)\n(.*?)\nEND_(?:TERRAFORM|TEXT)"

        matches = re.findall(pattern, response, re.DOTALL)

        for filename, content in matches:

            files[filename.strip()] = content.strip()

        return files