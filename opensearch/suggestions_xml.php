<?php
/*
 * Hitchwiki Maps: opensearch/suggestions_xml.php
 * Outputs suggestions list in opensearch xml format
 */


# NOTE; HERE FOR REFERENCE PURPOSE ONLY, NOT IN USE CURRENTLY. SEE suggestions.php INSTEAD (IN JSON FORMAT)


/*
 * Load config
 */
require_once "../config.php";

header ("content-type: text/xml");

echo '<?'; ?>xml version="1.0" encoding="utf-8"?>
<SearchSuggestion xmlns="http://opensearch.org/searchsuggest2" version="2.0">
	<Query><?php echo strip_tags($_GET["q"]); ?></Query>
	<Section title="<?php echo _("Results from Hitchwiki Maps"); ?>">
	<?php 
	
	if(!empty($_GET["q"])) {
	
		// Language
		$shortlang = (isset($_GET["lang"]) && !empty($_GET["lang"])) ? shortlang(strip_tags($_GET["lang"])) : shortlang();

		// Query
		$q = htmlspecialchars($_GET["q"]);

		$api_call = readURL("http://api.geonames.org/search?q=".urlencode($q)."&maxRows=10&lang=".urlencode($shortlang)."&style=short&username=".urlencode($settings["geonames"]["user"]));
			/* XML Responce example: 
                    [toponymName] => Lond
                    [name] => Lond
                    [lat] => 29.58263
                    [lng] => 66.45442
                    [geonameId] => 1171884
                    [countryCode] => PK
                    [fcl] => T
                    [fcode] => RDGE
			*/

		if(!empty($api_call)) {
			$xml = new SimpleXMLElement($api_call);

			foreach($xml->geoname as $location) {
				
				echo '
		<Item>
			<Text>'.htmlspecialchars($location->name).'</Text>
			<Description>';
			
			if(!empty($location->countryCode)) echo ISO_to_country($location->countryCode);
			
			echo '</Description>
			<Url>'.$settings["base_url"].'/?lat='.urlencode($location->lat).'&amp;lon='.urlencode($location->lng).'</Url>
		</Item>';
			#<Image source="http://.jpg" height="50" width="50" align="middle" />

			} // foreach
		} // !empty api_call 
	} // !empty q
	

	/*
		<Item>
			<Text>title</Text>
			<Description>desciption</Description>
			<Url><?php echo $settings["base_url"]; ?>/?place=</Url>
			<Image source="http://.jpg" height="50" width="50" align="middle" />
		</Item>
	*/ ?>
	</Section>
</SearchSuggestion>
