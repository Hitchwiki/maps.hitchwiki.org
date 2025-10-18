Deploment location: Hitchwiki server `/home/hitch`

<!-- PROJECT SHIELDS -->
<!--
*** Markdown "reference style" links for readability.
*** Reference links are enclosed in brackets [ ] instead of parentheses ( ).
*** See the bottom of this document for the declaration of the reference variables
*** for contributors-url, forks-url, etc. This is an optional, concise syntax you may use.
*** https://www.markdownguide.org/basic-syntax/#reference-style-links
-->
[![Contributors][contributors-shield]][contributors-url]
[![Issues][issues-shield]][issues-url]
[![Unlicense License][license-shield]][license-url]

<!-- ABOUT THE PROJECT -->
<div align="center">
  <h3 align="center">Hitchhiking Map</h3>
  <p align="center">
    The map to hitchhiking the world.
    <br />
    <br />
    <a href="https://github.com/Hitchwiki/hitch/issues/new?labels=bug&template=bug_report.md">Report Bug</a>
    &middot;
    <a href="https://github.com/Hitchwiki/hitch/issues/new?labels=enhancement&template=feature-request---.md">Request Feature</a>
  </p>
</div>

## About The Project

Read more [here](https://hitchwiki.org/en/Hitchwiki:Maps). This project embraces Nostr - hitchhiking rides that are submitted are published as Nostr event following the [data standard}(https://github.com/Hitchwiki/hitchhiking-data-standard) in the first place. So Nostr become the single source of truth (database) for hitchhiking rides that also other apps (not only this one) can contribute to.

Join the conversation about a map for hitchhiking in our [Signal Chat](https://signal.group/#CjQKIDyYgIxcOUCEPYu8-JawC_tv1bcgkAhvbISRZkN45MMVEhCtydy3DOOCKEAE_tsR6g9s).

### Fork and Divergence

This repository, [`Hitchwiki/hitchmap`](https://github.com/Hitchwiki/hitchmap), is a fork of [`bobjesvla/hitch`](https://github.com/bopjesvla/hitch).

## Getting Started

Set up Python virtual environment, install requirements and download the latest database dump:

Works with Python 3.12.6

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
curl https://hitchmap.com/dump.sqlite > db/points.sqlite
curl https://hitchmap.com/dump.sqlite > db/prod-points.sqlite
```

```
cp example.env .env
cp user-password.py.example user-password.py
```
And set the missing env variables.

Put file from `https://simplemaps.com/static/data/world-cities/basic/simplemaps_worldcities_basicv1.901.zip` into `dist/` as `worldcities.zip` but any `csv` file with `city`, `country`, `population` column works.

Initialize and run the Flask server:

```bash
flask init
flask run
```

In order to run the project continuously, use `cron.sh` to set up corresponding cronjobs to update the views and `hitchmap.conf` as a basic NGINX 
configuration.

### Deploy with Docker

```
sudo docker build -t hitch .
sudo docker run -p 5000:5000 --name hitchhiking-map -d hitch
# or
sudo docker compose up --build -d

sudo docker exec -it hitchhiking-map /bin/bash  

sudo docker stop hitchhiking-map 
sudo docker rm hitchhiking-map 
```

Serving with Apache

```shell
sudo cp apache.conf /etc/apache2/sites-available/25-hwmaptest.conf
```

```shell
# install the following
sudo a2enmod proxy
sudo a2enmod proxy_http
sudo a2enmod headers

# to start the deployment
sudo apachectl configtest
sudo systemctl reload apache2
```

## Data
If you find the data collected and provided by hitchmap.com helpful, feel free to cite it using:
```
@misc{hitchhiking,
author = {Till Wenke},
title = {Dataset of Hitchhiking Trips},
year = {2024},
url = {https://maps.hitchwiki.org},
}
```

## License

The software provided in this repository is licensed under AGPL 3.0. The Hitchmap database is licensed under the ODBL, the license used by OpenStreetMap.

<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->
[contributors-shield]: https://img.shields.io/github/contributors/Hitchwiki/hitchmap.svg?style=for-the-badge
[contributors-url]: https://github.com/Hitchwiki/hitchmap/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/Hitchwiki/hitchmap.svg?style=for-the-badge
[forks-url]: https://github.com/Hitchwiki/hitchmap/network/members
[stars-shield]: https://img.shields.io/github/stars/Hitchwiki/hitchmap.svg?style=for-the-badge
[stars-url]: https://github.com/Hitchwiki/hitchmap/stargazers
[issues-shield]: https://img.shields.io/github/issues/Hitchwiki/hitchmap.svg?style=for-the-badge
[issues-url]: https://github.com/Hitchwiki/hitchmap/issues
[license-shield]: https://img.shields.io/github/license/Hitchwiki/hitchmap.svg?style=for-the-badge
[license-url]: https://github.com/Hitchwiki/hitchmap/blob/master/LICENSE.txt
[Flask]: https://img.shields.io/badge/flask-000000?style=for-the-badge&logo=flask&logoColor=white
[Flask-url]: https://flask.palletsprojects.com/en/stable/

# Development

CONTRIBUTING.md

Install pre-commit

install ruff
