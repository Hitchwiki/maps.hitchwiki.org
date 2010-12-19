#!/bin/zsh

for lang (de_DE ru_RU ro_RO fi_FI pt_PT nl_NL zh_CN lt_LT pl_PL) {
    short=`echo -n $lang | perl -pe 's/^(..)_.+$/$1/g'`
    wget -o /dev/null http://hitchwiki.org/translate/projects/maps/$short/$lang/export-translations -O /tmp/$short.po
    msgfmt -o locale/$lang/LC_MESSAGES/maps.mo /tmp/$short.po
    mv /tmp/$short.po locale/$lang/LC_MESSAGES/maps.po -f

}
