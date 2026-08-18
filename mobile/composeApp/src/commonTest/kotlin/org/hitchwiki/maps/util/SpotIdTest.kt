package org.hitchwiki.maps.util
import kotlin.test.Test
import kotlin.test.assertEquals

class SpotIdTest {
    @Test fun formatsFiveDecimals() {
        assertEquals("51.08170_13.73629", spotId(51.0817001, 13.7362899))
    }
    @Test fun padsTrailingZeros() {
        assertEquals("38.65081_68.76809", spotId(38.65081, 68.76809))
    }
    @Test fun handlesNegative() {
        assertEquals("-33.86880_151.20930", spotId(-33.8688, 151.2093))
    }
}
