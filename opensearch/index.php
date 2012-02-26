<?php
/*
 * Hitchwiki Maps: opensearch/index.php
 * Outputs an opensearch XML description
 *
 * http://www.opensearch.org/
 */

/*
 * Load config
 */
require_once "../config.php";

header ("content-type: text/xml");

// Language
$lang = (isset($_GET["lang"]) && !empty($_GET["lang"])) ? htmlspecialchars($_GET["lang"]) : $settings["language"];

echo '<?'; ?>xml version="1.0" encoding="utf-8"?>
<OpenSearchDescription xmlns="http://a9.com/-/spec/opensearch/1.1/" xmlns:moz="http://www.mozilla.org/2006/browser/search/">
	<ShortName>Hitchwiki <?php echo htmlspecialchars(_("Maps")); ?></ShortName>
	<Description>Hitchwiki.org - <?php echo htmlspecialchars(_("Find good places for hitchhiking and add your own")); ?></Description>
	<Contact><?php echo protect_email($settings["email"]); ?></Contact>
	<Tags><?php echo htmlspecialchars(_("hitchhiking")." "._("traveling")." "._("maps")); ?></Tags>
	<Language><?php echo langcode($lang); ?></Language>
	<OutputEncoding>UTF-8</OutputEncoding>
	<InputEncoding>UTF-8</InputEncoding>
	<AdultContent>false</AdultContent>
	<Image height="16" width="16" type="image/png"><?php echo $settings["base_url"]; ?>/favicon.png</Image>
	<Image height="16" width="16" type="image/vnd.microsoft.icon"><?php echo $settings["base_url"]; ?>/favicon.ico</Image>
 	<Url type="text/html" method="get" template="<?php echo $settings["base_url"]; ?>/?src=opensearch&amp;lang=<?php echo urlencode($lang); ?>&amp;q={searchTerms}"/>
<?php/*	<Url type="application/x-suggestions+xml" template="<?php echo $settings["base_url"]; ?>/opensearch/suggestions.php?format=xml&amp;lang=<?php echo urlencode($lang); ?>&amp;q={searchTerms}"/>*/?>
	<Url type="application/x-suggestions+json" template="<?php echo $settings["base_url"]; ?>/opensearch/suggestions.php?format=json&amp;lang=<?php echo urlencode($lang); ?>&amp;q={searchTerms}"/>
	<Url type="application/opensearchdescription+xml" rel="self" template="<?php echo $settings["base_url"]; ?>/opensearch/?lang=<?php echo urlencode($lang); ?>"/>
	<Query role="example" searchTerms="Berlin" />
	<SyndicationRight>open</SyndicationRight>
	<moz:SearchForm><?php echo $settings["base_url"]; ?>/</moz:SearchForm>
	<Attribution><?php echo htmlspecialchars(_("Licensed under a Creative Commons Attribution-ShareAlike 3.0 Unported License")); ?></Attribution>
</OpenSearchDescription>