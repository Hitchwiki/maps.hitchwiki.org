<?php
/*
 * Hitchwiki Maps: contact.php
 * Handle contact us -messages
 */

/*
 * Load config to set language and stuff
 */
require_once "../config.php";

if(isset($_POST) && !empty($_POST)) {

	$subject = 'a message from Hitchwiki Maps';

	// Message	
	$message = '<html><head><title>Hitchwiki Maps</title></head><body>';
	$message .= "<h4>Message:</h4>\n\n".htmlspecialchars(stripslashes($_POST["message"]))."<br /><br />\n\n<b>From:</b> ".htmlspecialchars($_POST["email"])."<br />\n<b>IP:</b> ".$_SERVER['REMOTE_ADDR']."<br /><br />\n\n";

	// Add info about logged in user	
	$user = current_user();
	if($user !== false) $message .= "<h4>User:</h4>\n\n<pre>".print_r($user,true)."</pre><br /><br />\n\n";
	
	if(isset($_POST["log"]) && !empty($_POST["log"])) $message .= "<h4>Usage log:</h4>\n\n".stripslashes($_POST["log"])."<br /><br />\n\n";
	
	$message .= '<p><a href="'.$settings["base_url"].'">'.$settings["base_url"].'</a></p></body></html>';
	
	if(isset($_POST["source"]) && !empty($_POST["source"])) $message .= "<h4>Sent from:</h4>\n\n".stripslashes($_POST["source"])."<br /><br />\n\n";
	
	// From + send it
	if(isset($_POST["email"]) && !empty($_POST["email"])) $from = $_POST["email"].",";
	else $from = "";

	// To send HTML mail, the Content-type header must be set (we need html for the log)
	$headers  = 'MIME-Version: 1.0' . "\r\n";
	$headers .= 'Content-type: text/html; charset=UTF-8' . "\r\n";
	
	// Additional headers
	$headers .= 'From: ' . $settings["email"] . "\r\n";
	$headers .= 'Reply-To: ' . $from . $settings["email"] . "\r\n";
	$headers .= 'X-Mailer: PHP/' . phpversion() . "\r\n";
	
	mail($settings["email"], $subject, $message, $headers);

	$output["success"] = true;
}
else $output["error"] = true;

if(!$ajax_include) echo json_encode($output);

?>