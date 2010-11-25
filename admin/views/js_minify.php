<?php
/*
 * Hitchwiki Maps Admin: js_minify.php
 *
 * This is a tool to pack + combine javascript files used by Hitchwiki Maps
 * Run it once you've edited any of these files
 */

if(isset($user) && $user["admin"]===true): 


/*
 * Files you want to minify + combine
 */ 
$js_path = '../static/js/';
$js_files = array(
	#"jquery.min.js",
	#"jquery-ui.custom.min.js",
	#"jquery.pstrength-min.1.2.js",
	#"jquery.json-2.2.min.js",
	"jquery.cookie.js",
	"jquery.gettext.js",
	"main.js"
);
$output = 'min.js';

?>

<h1>Optimize JavaScript</h1>
<small>Uses <a href="http://code.google.com/closure/compiler/">Google Closure Compiler</a></small><br />
<br />

<?php
// Do the packing
if(isset($_POST["pack"])) {

	$script = "";
	foreach ($js_files as $js_file) {
		
		$filesize = filesize($js_path.$js_file);
		$packing_log .= '&bull; ' . $js_file . ' (' . $filesize . ' bytes)<br />';
		
		$total_scriptsize += $filesize;
		
		$script .= file_get_contents($js_path.$js_file)."\n\n";
	}

	$post_fields = array(
	    'compilation_level' => 'WHITESPACE_ONLY',
	    'output_format' => 'text',
	    'output_info' => 'compiled_code',
		'js_code' => $script
	);
	$url = 'http://closure-compiler.appspot.com/compile';
	
	$inputdata = array();
	foreach($post_fields as $key => $val){
	    $inputdata[] = $key."=".urlencode($val);
	}
	$query = implode("&", $inputdata);
	$ch = curl_init($url);
	curl_setopt($ch, CURLOPT_HEADER, 0);
	curl_setopt($ch, CURLOPT_POST, 1);
	curl_setopt($ch, CURLOPT_POSTFIELDS, $query);
	curl_setopt($ch, CURLOPT_FOLLOWLOCATION, 0);
	curl_setopt($ch, CURLOPT_REFERER, "http://maps.hitchwiki.org");
	curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
	$packed = curl_exec($ch);
	$curl_log = curl_getinfo($ch);
	curl_close($ch);

	file_put_contents($js_path.$output, $packed);
	
	$new_scriptsize = filesize($js_path.$output);
	
	?>
	<div class="ui-state-highlight ui-corner-all" style="padding: 0 .7em; margin: 20px 0;"> 
	    <p><span class="ui-icon ui-icon-info" style="float: left; margin-right: .3em;"></span> 
		<?php
		echo '<h3>Scripts packed: <a href="' . $js_path . $output . '">'.$output.'</a></h3>';
		echo '<blockquote>'.$packing_log;
		echo '<br /><b>Total original:</b> ' . $total_scriptsize . ' bytes';
		echo '<br /><b>Packed:</b> ' . $new_scriptsize . ' bytes';
		echo '<br /><b>' . round( (100*($total_scriptsize-$new_scriptsize))/$total_scriptsize ) . '% of the original</b>';
		echo '</blockquote>';
		?>
	    </p>
	</div>
	<br />
	
	<h2>Re optimize</h2>
	<?php
}

?>

<form method="post" action="./?page=js_minify">
	<b>Files to be packed into a file <i><a href="<?php echo $js_path.$output; ?>"><?php echo $output; ?></a></i>:</b><br />
	<?php
	// List files
	foreach ($js_files as $js_file) {
		echo ' &bull; <a href="'.$js_path.$js_file.'">' . $js_file . '</a><br />';
	}
	?>
	<br /><br />
	<button type="submit" name="pack"><span class="icon link"></span>Optimize</button>
</form>


<?php
// Echo log
if(isset($curl_log)) {
	echo '<br /><br /><b>cURL info:</b><small><br /><pre>';
	print_r($curl_log);
	echo '</pre></small>';
}
?>

<?php endif; ?>