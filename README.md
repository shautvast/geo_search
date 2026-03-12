# Geosearch
**An geolocation agent**
* uses Claude API to extract features from images and drive the agent
* use OpenStreetMap data via the Overpass API
* use serpapi to find info on non-geographic items
* allows human intervention for extra prompts

The results are pretty ok. The loop narrows in on the location, 
but if there are no hits, it zooms out or traverses sideways. 

The test data is provided for humans to get a feel of how it works. They are screenshots from google.maps

### Running the agent:
`uv run agent main.py [image file]`

## Setup
The Overpass api is sadly not very stable. For that reason I chose to run it locally. That was quite a bit of work
I collected this info as well as possible, but I might have missed something...

### Overpass-API
Building the Overpass API works best on linux. Therefore I created an Ubunto VM on my mac using UTM. 
This works pretty smoothly given you have the right dependencies. 

#### UTM or other hypervisor
- using virtualisation, so build from source on ARM64
- ubuntu 24.04 (minimal)
- add extra virtual disk 64Gb (fits netherlands OSM database)
- port forwards 22->2222 80->80 5173->5173

```
sudo apt-get update
sudo apt install g++ make expat libexpat1-dev zlib1g-dev wget bzip2 libtool autoconf osmium-tool git apache2
git clone https://github.com/drolbr/Overpass-API.git
cd Overpass-API/src
autoreconf -fi
cd ../build
../src/configure --prefix="`pwd`"
make -j8
make install
cd ..
chmod u+x src/bin/init_osm3s.sh
wget https://download.geofabrik.de/europe/netherlands-260310.osm.pbf
osmium cat netherlands-260310.osm.pbf -o netherlands.osm.bz2
src/bin/init_osm3s.sh netherlands.osm.bz2 db build
```

#### system-ctl overpass-dispatcher
```
[Unit]
Description=Overpass API Dispatcher
After=local-fs.target network.target

[Service]
User=sander
ExecStart=/home/sander/Overpass-API/build/bin/dispatcher --osm-base --db-dir=/mnt/data/db
ExecStop=/path/to/bin/dispatcher --terminate
Restart=on-failure

[Install]
WantedBy=multi-user.target
```


#### optional: Overpass-turbo UI
Overpass-turbo frontend is not used by the agent.
I left this in just in case someone wants to integrate it.

```
git clone https://github.com/tyrasd/overpass-turbo.git
sudo apt install node nvm
nvm install 20
nvm use 20
cd overpass-turbo
```

in home/sander/overpass-turbo/js/config.ts:
`defaultServer: "http://localhost/api/",`
-> don't do this if you use the regular backends

`npm run build` Did not work
`npm run dev`
-> UI on http://localhost:5173

#### Apache 
in /etc/apache2/sites-available/overpass.conf:
```
<VirtualHost *:80>
ServerName localhost
DocumentRoot /home/sander/overpass-turbo/dist

    ScriptAlias /api/ /home/sander/Overpass-API/build/cgi-bin/

    <Directory "/home/sander/Overpass-API/build/cgi-bin/">
        Options +ExecCGI -MultiViews +SymLinksIfOwnerMatch
        AllowOverride None
        Require all granted


        Header always set Access-Control-Allow-Origin "*"
        Header always set Access-Control-Allow-Methods "GET, POST, OPTIONS"
        Header always set Access-Control-Allow-Headers "Content-Type"
    </Directory>

    <Directory "/home/sander/overpass-turbo/dist">
        AllowOverride All
        Require all granted

        Header always set Access-Control-Allow-Origin "*"
        Header always set Access-Control-Allow-Methods "GET, POST, OPTIONS"
        Header always set Access-Control-Allow-Headers "Content-Type"

    </Directory>
</VirtualHost>
```

-> The overpass turbo Directory is optional

```bash
sudo a2ensite overpass.conf
sudo systemctl restart apache2
```


_a human created this readme_