<h2><?php echo _("API Documentation"); ?></h2>

<a target="_blank" href="http://www.sxc.hu/photo/85875" title="Photo from SXC.hu by hiphop."><img src="static/gfx/api.jpg" alt="" class="align_right" style="margin: 0 0 20px 20px;" /></a>

<p>w00t? Yeah, you can now read Hitchwiki Maps database trough an open API! It's the same API we use at our JavaScript frontend.</p>

<p>API call base URL: <code class="highlight"><?php echo $settings["base_url"]; ?>/api/</code></p>

<p>API call base URL for demo purpose: <code class="highlight"><?php echo $settings["base_url_demo"]; ?>/api/</code><br />
<small><em>Use this when you want to test your program, since it uses a different database and changes won't go visible to the actual website.</em></small></p>


<h2><?php echo _("List of API-calls"); ?></h2>
<ul>
	<li><a href="#place_info">Place info</a></li>
	<li><a href="#places_area">List places from area</a></li>
	<li><a href="#places_city">List places by city</a></li>
	<li><a href="#places_country">List places by country</a></li>
	<li><a href="#places_continent">List places by continent</a></li>
	<li><a href="#continents">List of continents</a></li>
	<li><a href="#countries">List of countries</a></li>
	<li><a href="#languages">List of languages</a></li>
	<li><a href="#custom">Custom variables</a></li>
	<li><a href="#errors">Errors</a></li>
	<li><a href="#license">License</a></li>
</ul>


<h3 id="place_info">Place info</h3>

<code class="highlight">/api/?place=[ID]</code><br />
Get all info about place by ID.<br />
JSON Example:<br />
<code class="example"><pre>{
	"id":"355",
	"lat":"51.2029594207479",
	"lon":"4.38469022512436",
	"elevation":"7",
	"rating":"5",
	"rating_count":"1",
	"location":
	{
		"city":"Antwerp",
		"country":
		{
			"iso":"BE",
			"name":"Belgium"
		},
		"continent":
		{
			"code":"EU",
			"name":"Europe"
		}
	},
	"user":
	{
		"id":"10",
		"name":"Joe Doe"
	},
	"link":"http:\/\/maps.hitchwiki.org\/?place=355",
	"datetime":"2010-07-29 15:12:20",
	"description":
	{
		"en_UK":
		{
			"datetime":"2011-01-31 23:41:15",
			"fk_user":"12345",
			"description":"Lorem ipsum dolor sit amet.",
			"versions":"2"
		},
		"lt_LT":
		{
			"datetime":"2010-12-22 21:11:12",
			"fk_user":"12355",
			"description":"Loremė ipsumius dolor šites amet.",
			"versions":"1"
		},
	},
	"comments":
	{[
		{
			"id":"1",
			"comment":"Lorem ipsum dolor sit amet!",
			"datetime":"2010-07-30 14:45:57",
			"user":
			{
				"nick":"Joe Doe"
			}
		},
		{
			"id":"2",
			"comment":"Lorem ipsum test.",
			"datetime":"2010-07-30 15:12:20",
			"user":
			{
				"id":"1",
				"name":"Joe Doe"
			}
		}
	]},
	"comments_count":2
}</pre></code>
<br /><br />

<code class="highlight">/api/?place=[ID]&amp;dot</code><br />
Get very basic info about place by ID by adding a <span class="highlight">dot</span> to the query. Just what you might need to draw a point to the map.<br />
JSON Example:<br />
<code class="example"><pre>{
	"id":"355",
	"lat":"51.2029594207479",
	"lon":"4.38469022512436",
	"rating":"0"
}</pre></code>
<br /><br />


<h3 id="places_area">List places from area</h3>
<code class="highlight">/api/?bounds=59.375129767984,64.208716083434,22.544799804826,35.190063476196</code><br />
JSON Example:<br />
<code class="example"><pre>[
	{
		"id":"957",
		"lat":"61.4893999989479",
		"lon":"23.7795531749725",
		"rating":"2"
	},
	{
		"id":"1591",
		"lat":"61.1811048903562",
		"lon":"23.8870024681091",
		"rating":"1"
	},
	...

]</pre></code>
<br /><br />


<h3 id="places_city">List places by city</h3>
<code class="highlight">/api/?city=[CITYNAME IN ENGLISH]</code><br />
See an example from "List places from area"-section.
<br /><br />


<h3 id="places_country">List places by country</h3>
<code class="highlight">/api/?country=[COUNTRY ISO CODE]</code><br />
Get all places from a country by country ISO-code. <a href="<?php echo $settings["base_url"]; ?>/api/?countries=all&amp;format=string" target="_blank">See the list of codes</a>.
<br /><br />
See an example from "List places from area"-section.
<br />


<h3 id="places_continent">List places by continent</h3>
<code class="highlight">/api/?continent=[CONTINENT CODE]</code>
<ul>
	<?php
	$continents = list_continents();
	
	foreach($continents as $continent) {
		echo '<li><span class="highlight">'.$continent["code"].'</span>: '.$continent["name"].'</li>';
	}
	?>
</ul>
See an example from "List places from area"-section.
<br /><br />


<h3 id="continents">List of continents</h3>
<code class="highlight">/api/?continents</code>
<ul>
	<li>Short code
		<ul>
			<?php
			foreach($continents as $continent) {
				echo '<li>'.$continent["code"].': '.$continent["name"].'</li>';
			}
			
			?>
		</ul>
	</li>
	<li>Name</li>
	<li>Places count</li>
</ul>
JSON Example:<br />
<code class="example"><pre>{
	"AS":
	{
		"name":"Asia",
		"code":"AS",
		"places":"89"
	},
	"AF":
	{
		"name":"Africa",
		"code":"AF",
		"places":"19"
	},
	...
}</pre></code>
<br /><br />


<h3 id="countries">List of countries</h3>
List only countries with places: <br />
<code class="highlight">/api/?countries</code>
<br /><br />
List all countries, also with 0 places:<br />
<code class="highlight">/api/?countries=all</code>
<br /><br />
Get also country coordinates with <span class="highlight">coordinates</span>-variable:<br />
<code class="highlight">/api/?countries&amp;coordinates</code>


<ul>
	<li>ISO short code</li>
	<li>Name</li>
	<li>Places count</li>
	<li>Latitude (not by default)</li>
	<li>Longitude (not by default)</li>
</ul>
JSON Example with coordinates:<br />
<code class="example"><pre>{
	"Germany":
	{
		"iso":"DE",
		"name":"Germany",
		"places":"662"
	},
	"France":
	{
		"iso":"FR",
		"name":"France",
		"places":"423"
	},
	...
}</pre></code>
<br /><br />


<h3 id="languages">List of languages</h3>
Get a list of available languages.
<code class="highlight">/api/?languages</code>

<ul>
	<li>ISO code</li>
	<li>Language name in requested language (default en_UK)</li>
	<li>"In Language" in original language</li>
</ul>
JSON Example:<br />
<code class="example"><pre>{
	"en_UK":
	{
		"code":"en_UK",
		"name":"English",
		"name_original":"In English"
	},
	"de_DE":
	{
		"code":"de_DE",
		"name":"German",
		"name_original":"Auf Deutsch"
	},
	...
}</pre></code>
<br /><br />

<h3 id="errors">In case of error</h3>
If API produces an error, it returns "error":"true" and possible error description. 
<br /><br />
JSON Example where calling /api/?place=351 didn't find a place with this ID:<br />
<code class="example"><pre>
{
	"error":"true",
	"error_description":"Place not found."
}</pre></code>
<br /><br />

<h3 id="custom">Custom variables</h3>
Variables you can use with all API calls:
<ul>
	<li><strong class="highlight">lang</strong>: output countrynames and continents in certain language, available:
		<ul>
		<?php
			foreach($settings["valid_languages"] as $code => $lang) {
			
				echo '<li title="'.$lang.'"><span class="highlight">'.$code.'</span>: <img class="flag" alt="" src="static/gfx/flags/png/'.strtolower(substr($code, -2)).'.png" /> ' . $settings["languages_in_english"][$code];
				
				if($code == $settings["default_language"]) echo ' ('._("default").')';
				
				echo '</li>';
			}
		?>
		</ul>
	</li>
	<li><strong class="highlight">format</strong>: not required. By default API returns a JSON string, but you can ask for: <span class="highlight" title="JavaScript Object Notation">json</span>, <span class="highlight" title="Keyhole Markup Language">kml</span> and <span class="highlight">string</span> (for testing - it's just human readable rather than computer). NOTICE: KML format not functional yet.</li>
	<li><strong class="highlight">download</strong>: force to download as a file. If you add content to it, it's used as a filename. Eg. <span class="highlight">download=filename</span>. Default filename is "places" and ".json/kml/txt" will be added depending on requested format. Valid characters are "<i>a-zA-Z0-9._-</i>" and max 255 of them.</li>
	<li><strong class="highlight">who</strong>: it's not required, but would be lovely to see who uses our API. You can add unique string like service name, URL or email to this.</li>
</ul>
<br /><br />
Example, download a file "testfile.kml" with a place on it in Finnish:
<code class="highlight"><a href="<?php echo $settings["base_url"]; ?>/api/?id=355&amp;format=kml&amp;download=testfile&amp;lang=fi_FI&amp;who=Hitchwiki" target="_blank">/api/?id=355&amp;format=kml&amp;download=testfile&amp;lang=fi_FI&amp;who=Hitchwiki</a></code>
<br /><br />



<h3 id="license"><?php echo _("License"); ?></h3>
<a rel="license" href="<?php echo _("http://creativecommons.org/licenses/by-sa/3.0/"); ?>"><img alt="<?php echo _("Creative Commons License"); ?>" style="border-width:0" src="http://i.creativecommons.org/l/by-sa/3.0/88x31.png" /></a>
<br /><br />
<a rel="license" href="<?php echo _("http://creativecommons.org/licenses/by-sa/3.0/"); ?>"><?php echo _("Licensed under a Creative Commons Attribution-ShareAlike 3.0 Unported License"); ?></a>.

