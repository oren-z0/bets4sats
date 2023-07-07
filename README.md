# Bookie - <small>[LNbits](https://github.com/lnbits/lnbits) extension</small>
<small>For more about LNBits extension check [this tutorial](https://github.com/lnbits/lnbits/wiki/LNbits-Extensions)</small>

## Sell tickets for bets on competitions and send back rewards with ease

Bookie alows you to make tickets for bets on competitions.
Each user chooses an option to bet on, fills a lightning-address to receive the
winning reward, and sends an amount of sats.
When the competition ends, the app-manager selects the option that won, and all
the rewards will be sent automatically from the wallet to the winners' lightning
addresses, proportionally to the size of their bets.
The app manager keeps 1% of the rewards. Lightning fees are deducted from the users.

Bookie includes a shareable ticket scanner, which can be used to find the tickets
in case of disputes.

## Usage

1. Create a new competition\
   ![new competition](https://i.imgur.com/Y1DUahK.jpeg)
2. Fill out the competition information:

   - competition name
   - wallet (normally there's only one)
   - competition information
   - banner url (optional)
   - choices
   - minimum bet and maximum bet for each ticket
   - ticket selling closing date (universal time clock)
   - amount of tickets to sell

   Once the competition has been created, you can only modify the ticket closing date
   and the amount of tickets. The other competition details cannot be modified!

   ![competition info](https://i.imgur.com/F9N7woa.png)

3. Share the competition registration link\
   ![competition ticket](https://i.imgur.com/Nwkpf96.png)

   - ticket purchase example \
     ![ticket example](https://i.imgur.com/q2SrFMU.png)

   - QR code ticket, presented after invoice paid\
     ![competition ticket](https://i.imgur.com/CZCL9LY.png)

4. Use the built-in ticket scanner to see all competition tickets and find them
via the QR code\
   ![ticket scanner](https://i.imgur.com/0FXH5mc.png)

5. In the main competitions table, scroll right and click the pen icon to edit a competition\
    ![edit competition](https://i.imgur.com/CbIbNrX.png)

6. Choose a winner, automatically pay all the rewards. Failed payments will be
mentioned in the tickets table, so you could see them when the ticket owners
contact you. ![complete competition](https://i.imgur.com/XO4Esgd.png)

## Credit

Created by: [Oren-Z0](https://github.com/oren-z0)

Logo:
Icons made by [Freepik](https://www.flaticon.com/authors/freepik) from
[www.flaticon.com](https://www.flaticon.com).

This project was forked from [Events](https://github.com/lnbits/events)
by [Ben Arc](https://github.com/benarc)
