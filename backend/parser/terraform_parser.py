class TerraformParser:

    def parse(self, response: str):

        files = {}

        current_file = None
        content = []

        for line in response.splitlines():

            if line.startswith("###"):

                if current_file:
                    files[current_file] = "\n".join(content).strip()

                current_file = line.replace("###", "").strip()

                content = []

            else:

                content.append(line)

        if current_file:

            files[current_file] = "\n".join(content).strip()

        return files