[![generate docs](https://github.com/NOWUM/entso-monitor/actions/workflows/generate-docs.yml/badge.svg)](https://github.com/NOWUM/entso-monitor/actions/workflows/generate-docs.yml)

# [DEPRECATED] ENTSO-E and ENTSO-G Monitor

This is a software project developed for the AMI Master at FH Jülich.

> [!IMPORTANT]  
> Use the newer [Open-Energy-Data-Server](https://github.com/open-energy-data-server/open-energy-data-server) instead.

## running the software

the software should be deployed with docker or directly as a python file

The databases must be created by running the crawl_cron.py file.

The visualization also needs to load map-data from ENTSOG.
This needs the execution of the script entsog_maploader.py

## Update Database regularly with Cron

You can create a cronjob on the host to run

`docker exec entso-dashboard python crawl_cron.py > /usr/bin/logger -t entso-monitor`

this will run the given script in the docker container

## Documentation

The first documentation was created by running:

`sphinx-apidoc -o docs -H ENTSOE/G-Monitor -A "Florian Maurer" -V 0.1 -Fa entsoe_data`

then adjusting the files accordingly, adding the numpydoc extension and the rtd theme.

This documentation can be now updated easily by running `make html` in the docs folder, which produces the great output.

This can be seen locally by running `python -m http.server -d ./_build/html 8080` from the docs folder.
