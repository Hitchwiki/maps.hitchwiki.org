<h2><?php echo _("News"); ?></h2>

<div style="width: 650px;">


<b><small class="light">27. November 2010</small></b><br />
<h3 style="display:inline;">Ooh! New Maps!</h3><br />
<img src="badge.png" alt="" class="align_right" style="margin: 0 0 20px 20px;" />
Good day to you all. It was about time to take our great Maps service and make it even better! And shiny! And orange.
<br  /><br />
It's not anymore just about you and your hitchhiking places, but everybody can comment, rate and contribute. Just like in our Wiki. Still it's not a Facebook... it's not blue you know. We tried our best to make it as usable and good (and orange) as possible. 
<br /><br />
We now also have a <a href="http://www.facebook.com/hitchwiki/" title="Go to Facebook">Hitchwiki Facebook Page</a>, to where you can join in and get recent updates about Hitchwiki with ease. Even better, head to our new <a href="http://hitchwiki.org/community/groups/maps/">Community</a> where you can share your thoughts about Maps.
<br /><br />
Ok. Ta. Be well.
<br /><br />
PS. You can show your love to us and recommend Hitchwiki Maps to your <br />
hitchhiker mates in Facebook by pressing this cute little button with a familiar icon on it:
<br /><br />
<?php
if(strstr($_SERVER['HTTP_USER_AGENT'], "Opera")): ?>
	<fb:like layout="standard" href="<?php echo urlencode($settings["base_url"]); ?>">
<?php else: ?>
	<fb:comments xid="<?php echo urlencode($settings["base_url"]); ?>" numposts="5" width="650" publish_feed="true"></fb:comments>
<?php endif; ?>


<script type="text/javascript">
    $(function() {
    	FB.XFBML.parse(document.getElementById('pages'));
    });
</script>

</div>