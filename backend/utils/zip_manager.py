import shutil


def create_zip(project_path):

    zip_path = shutil.make_archive(project_path, "zip", project_path)

    return zip_path