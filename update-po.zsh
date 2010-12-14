#!/bin/zsh

for lang (de_DE ru_RU fi_FI pt_PT nl_NL zh_CN) {
    short=`echo -n $lang | perl -pe 's/^(..)_.+$/$1/g'`
    wget http://hitchwiki.org/translate/projects/maps/$short/$lang/export-translations -O /tmp/$short.po
    msgfmt -o locale/$lang/LC_MESSAGES/maps.mo /tmp/$short.po
    rm /tmp/$short.po

}
