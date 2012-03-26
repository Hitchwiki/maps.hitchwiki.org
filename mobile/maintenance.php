<!DOCTYPE HTML>
<html lang="en-US">
<head>
	<meta charset="utf-8">
	<title>Hitchwiki Maps</title>
	<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=0">
	<meta name="apple-mobile-web-app-capable" content="yes">
	<style>

html ,
body {
    margin: 0;
    padding: 0;
    height: 100%;
    font-family: arial,sans-serif;
}
	</style>
    <?php
    	if(isset($_GET["maintenance"])) echo '<meta http-equiv="refresh" content="300;url='.$settings["base_url"].'/?post_maintenance">';
    	else echo '<meta http-equiv="refresh" content="300;url=./?post_maintenance">';
    ?>
</head>
<body>

	<div style="padding: 15px; text-align: center;">
		<h3>Hitchwiki Maps</h3>
		<h2>Maintenance break!</h2>
		<p><strong><em>Hey folks!<br />We try to make our best to get Maps up and running again!</em></strong></p>
	</div>

</body>
</html>