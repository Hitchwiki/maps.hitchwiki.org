<?php
/*
 * Hitchwiki Maps Admin: translate_languagenames.php
 *
 * A tool with you can list countrynames in certain language
 *
 */

if(isset($user) && $user["admin"]===true): 

start_sql();
?>


<h2>Translate countrynames</h2>

<?php

# Limit to use with XML-request
#if(isset($_GET["limit"]) && !empty($_GET["limit"])) $limit = htmlspecialchars($_GET["limit"]);
#else $limit = false;

if(isset($_POST["locale"]) && !empty($_POST["locale"])) $locale = htmlspecialchars($_POST["locale"]);
elseif(isset($_POST["locale_txt"]) && !empty($_POST["locale_txt"])) $locale = htmlspecialchars($_POST["locale_txt"]);
else $locale = false;

if(isset($_POST["iso"]) && !empty($_POST["iso"])) $locale_short = htmlspecialchars($_POST["iso"]);
else $locale_short = false;

if($locale_short != false && $locale != false) {
	
	// Get data
	$i=0;
	$data = readURL("http://ws.geonames.org/countryInfoCSV?lang=".strtolower($locale_short));
	$lines = explode("\n",$data);
	$query_log = "";
	foreach($lines as $num => $line) {
		if($num != 0 && !empty($line)) {
			$line = explode("\t",$line);
			
			if(!empty($line[4])) {
				$query = "UPDATE `t_countries` SET `".$locale."` = '".mysql_real_escape_string( $line[4] )."' WHERE `iso` = '".$line[0]."'";//;\n
				
				$query_log .= '<span style="font-family: courier,serif;">'.$query.'</span>';
				
				if(isset($_POST["sql_update"]) && $_POST["sql_update"] == "1") {
					$result = mysql_query($query);
					if(!$result) {
						$query_log .= ' - <b style="color: darkred;">ERROR</b> '.mysql_error();
					} else {
						$query_log .= ' - <b style="color: darkgreen;">UPDATED</b>';
					}
				}
				$query_log .= '<br />';
				$result = false;
				
			}
		}
	}
	
	// To the DB?
	/*
	if(isset($_POST["sql_update"]) && $_POST["sql_update"] == "1") {

		
		if ($sql_error) {
			?>
			<div class="ui-state-error ui-corner-all" style="padding: 0 .7em; margin: 20px 0;"> 
			    <p><span class="ui-icon ui-icon-alert" style="float: left; margin-right: .3em;"></span> 
			    <strong><?php echo _("Alert"); ?>:</strong> MySQL query failed!</p>
			</div>
			<?php
		} else {
			?>
			<div class="ui-state-highlight ui-corner-all" style="padding: 0 .7em; margin: 20px 0;"> 
			    <p><span class="ui-icon ui-icon-info" style="float: left; margin-right: .3em;"></span> 
			    	<?php echo $lang_count; ?> languages updated to the database.
			    </p>
			</div>
			<?php
		}
	}
	*/
	
	
	// Echo out
	echo '<hr />'. $query_log .'<hr />';

	echo '<h2>Re-translate</h2>';
} 

?>


<form method="post" action="./?page=translate_countrynames">

	<label for="iso">Language code:</label> <input type="text" size="2" value="<?php if(!empty($locale_short)) echo htmlspecialchars($locale_short); ?>" name="iso" id="iso" /><br />
	<small>In <a href="http://en.wikipedia.org/wiki/ISO_639-1">ISO 639-1</a> language code format. Lowercase. eg. "de" for German</small>
	<br /><br />
	<label for="locale">Language locale:</label> <select name="locale" id="locale"><option value="">Select</option>
		<?php 
			// List languages from config.php
			foreach($settings["valid_languages"] as $code => $language) {
				echo '<option value="'.$code.'"';
				if($locale == $code) echo ' selected="selected"';
				echo '>'.$code.' ('.$language.')</option>';
			}
		?>
	</select>
	 
	<i>or</i>
	 
	<input type="text" size="5" value="<?php if(!empty($locale)) echo htmlspecialchars($locale); ?>" name="locale_txt" id="locale_txt" /><br />
	<small><a href="http://en.wikipedia.org/wiki/ISO_639-1">ISO 639-1</a> and <a href="http://en.wikipedia.org/wiki/ISO_3166-1_alpha-2#Officially_assigned_code_elements">Alpha-2</a> seperated with underscore (_). eg. "de_DE" for German</small>
	<br /><br />
	
	<input type="checkbox" value="1" name="sql_update" id="sql_update" <?php if(isset($_POST["sql_update"]) && $_POST["sql_update"] == "1") echo ' checked="checked"'; ?> /> <label for="sql_update">Update results to the SQL database?</label><br />
	<small>Remember to first <a href="./?page=new_language">add new language</a> to the DB!</small>
	
	<br /><br />
	
	<input type="submit" value="Translate" class="button" />

</form>

<?php endif; // use check ?>